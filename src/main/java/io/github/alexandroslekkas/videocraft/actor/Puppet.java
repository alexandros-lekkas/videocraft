package io.github.alexandroslekkas.videocraft.actor;

import io.github.alexandroslekkas.videocraft.VideocraftLog;
import io.github.alexandroslekkas.videocraft.api.Actor;
import io.github.alexandroslekkas.videocraft.api.Params;
import io.github.alexandroslekkas.videocraft.api.ShotContext;
import io.github.alexandroslekkas.videocraft.mixin.actor.EntityAccess;
import io.github.alexandroslekkas.videocraft.mixin.actor.FoxAccess;
import io.github.alexandroslekkas.videocraft.mixin.actor.LivingEntityAccess;
import io.github.alexandroslekkas.videocraft.mixin.actor.MobAccess;
import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.resources.Identifier;
import net.minecraft.sounds.SoundEvent;
import net.minecraft.sounds.SoundEvents;
import net.minecraft.util.ProblemReporter;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.EntitySpawnReason;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.entity.EquipmentSlot;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.Mob;
import net.minecraft.world.entity.TamableAnimal;
import net.minecraft.world.entity.ai.attributes.Attributes;
import net.minecraft.world.entity.animal.feline.Cat;
import net.minecraft.world.entity.animal.fox.Fox;
import net.minecraft.world.entity.animal.goat.Goat;
import net.minecraft.world.entity.decoration.Mannequin;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.storage.TagValueInput;
import net.minecraft.world.phys.Vec3;
import net.minecraft.world.phys.shapes.VoxelShape;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Random;
import java.util.TreeSet;

/**
 * A scripted character that is not the player: a mob ({@code kind = "mob"}, any living entity) or a player-shaped
 * Mannequin ({@code kind = "mannequin"}). It is a client-side entity (a negative id the server never hears of), so
 * nothing but the script moves it: no AI, no gravity surprises, no despawning, no pushing.
 *
 * <p><b>Deterministic.</b> The level never ticks it ({@code mixin.actor.PuppetTickMixin}); the puppet ticks it itself
 * at 20 Hz on the take's frame clock, and the renderer draws it at the puppet's own fraction of a tick
 * ({@code PuppetRenderMixin}), not the real-time one. So where it is, how its legs swing and what its own animations do
 * (a fox's crouch, a goat lowering its head, a chicken's wings) are a function of the plan, the seed and the frame.
 *
 * <p><b>Alive.</b> Each tick it moves along its walk ({@link Stride} on a {@link Path}), finds the ground under it
 * ({@link Footing}), turns head first and body after ({@link Heading}), glances about between beats ({@link Life}),
 * and then lets the entity's own tick run: so the walk cycle is vanilla's own, from the distance it really moved, and
 * the entity's own idle animations play. Footsteps are its own step sound on the block it treads, at vanilla's cadence.
 */
public final class Puppet implements Actor {
	private static int nextId = -7_700_000;
	static final double TICK = 0.05;

	final String id, kind, entityId;
	private final Params spec;
	final Breed breed;
	private final Random random;
	private LivingEntity entity;
	private int fps = 60, frames;
	private long ticks;
	private float phase;
	private double now;

	// Where it is (at the end of the last tick) and where it was (the tick before): drawn in between.
	private double x, z;
	private final Footing foot = new Footing();
	private Heading heading;
	private final Life life;
	private Stride stride;
	private String gait = "walk";
	private double prevX, prevY, prevZ, prevG, curX, curY, curZ, curG;
	private float prevBody, curBody, prevHead, curHead, prevPitch, curPitch;
	private boolean spawned;
	// Until the script first moves it, a puppet stands on its `at`, whatever staging builds under it meanwhile.
	private boolean pristine = true;
	private double spawnY;

	// Scripted state.
	private final TreeSet<String> states = new TreeSet<>();
	final List<Gesture> gestures = new ArrayList<>();
	private double flapUntil = -1, chinOverride = Double.NaN;
	private final List<Prop> props = new ArrayList<>();
	private int tint = -1;

	Puppet(Spec spec) {
		this.id = spec.id;
		this.kind = spec.kind;
		this.spec = spec.params;
		this.entityId = spec.entity;
		this.breed = Breed.of(entityId);
		this.random = new Random(spec.seed * 0x9E3779B97F4A7C15L ^ id.hashCode());
		this.life = new Life(new Random(random.nextLong()), temper(spec.params));
		this.heading = new Heading(0, breed.reach(), new Random(random.nextLong()));
	}

	/** What Cast hands over: the actor's id, kind, entity id, its script parameters and the take's seed. */
	record Spec(String id, String kind, String entity, Params params, long seed) {}

	private static Life.Temper temper(Params p) {
		String life = p.string("life", "");
		return switch (life) {
			case "" -> null;
			case "off" -> Life.Temper.OFF;
			case "calm" -> Life.Temper.CALM;
			case "busy" -> Life.Temper.BUSY;
			default -> throw new IllegalArgumentException(p.where() + ": life is \"calm\", \"busy\" or \"off\", not '" + life + "'");
		};
	}

	// ---- Actor ----

	@Override public String id() { return id; }
	@Override public Entity entity() { return entity; }

	@Override
	public Vec3 ground() {
		return new Vec3(lerp(prevX, curX), lerp(prevG, curG), lerp(prevZ, curZ));
	}

	@Override
	public float heading() { return rotLerp(prevBody, curBody); }

	@Override
	public Vec3 head() {
		double eye = entity == null ? 1 : entity.getEyeHeight();
		return new Vec3(lerp(prevX, curX), lerp(prevY, curY) + eye, lerp(prevZ, curZ));
	}

	@Override
	public Vec3 velocity() { return new Vec3((curX - prevX) / TICK, 0, (curZ - prevZ) / TICK); }

	/** The yaw the head faces now, and its pitch. */
	public float headYaw() { return rotLerp(prevHead, curHead); }

	public float headPitch() { return (float) lerp(prevPitch, curPitch); }

	/** The feet as drawn this frame, a hop included (unlike the camera's {@link #ground()}). */
	public double feetY() { return lerp(prevY, curY); }

	@Override
	public void frame(ShotContext shot) {
		fps = shot.fps();
		if (!spawned) spawn(shot);
		if (entity == null) return;
		if (entity.isRemoved() || entity.level() != shot.minecraft().level) respawn(shot.minecraft());
		frames++;
		now = frames / (double) fps;
		double t = frames * 20.0 / fps;
		long target = (long) Math.floor(t + 1e-9);
		while (ticks < target) {
			ticks++;
			tick(shot);
		}
		phase = (float) (t - ticks);
		if (shot.recording()) ActorLog.row(shot, this);
	}

	@Override
	public void cut(ShotContext shot) {
		ActorLog.write(shot);
	}

	// ---- Staging ----

	private void spawn(ShotContext shot) {
		spawned = true;
		Minecraft mc = shot.minecraft();
		Vec3 at = shot.position(spec, "at");
		x = at.x;
		z = at.z;
		spawnY = at.y;
		create(mc, at.y);
		double yaw = spec.has("facing") ? Actions.facing(this, shot, spec, at) : 0;
		heading = new Heading(yaw, breed.reach(), new Random(random.nextLong()));
		foot.place(orElse(groundAt(x, z, at.y, true), at.y));
		snapshot();
		snapshot();
		apply(true);
		VideocraftLog.LOGGER.info("VIDEOCRAFT actor {} {} at {} {} {} facing {}", id, entityId, String.format(Locale.ROOT, "%.2f", x), String.format(Locale.ROOT, "%.2f", foot.y()), String.format(Locale.ROOT, "%.2f", z), yaw);
	}

	private void create(Minecraft mc, double y) {
		net.minecraft.client.multiplayer.ClientLevel level = mc.level;
		EntityType<?> type = BuiltInRegistries.ENTITY_TYPE.getOptional(Identifier.parse(entityId))
			.orElseThrow(() -> new IllegalArgumentException(spec.where() + ": no entity '" + entityId + "'"));
		Entity made = type.create(level, EntitySpawnReason.COMMAND);
		if (!(made instanceof LivingEntity living)) throw new IllegalArgumentException(spec.where() + ": '" + entityId + "' is not a living entity");
		CompoundTag tag = Looks.tag(this, spec);
		living.load(TagValueInput.create(ProblemReporter.DISCARDING, level.registryAccess(), tag));
		living.setId(nextId--);
		living.setPos(x, y, z);
		living.setOldPosAndRot();
		living.setPermanentlyInvulnerable(true);
		living.setNoGravity(true);
		living.getRandom().setSeed(random.nextLong());
		if (living instanceof Mob mob) { mob.setNoAi(true); mob.setPersistenceRequired(); }
		double scale = spec.number("scale", 1);
		if (scale != 1) {
			if (scale < 0.0625 || scale > 16) throw new IllegalArgumentException(spec.where() + ": scale is 0.0625 to 16");
			var attribute = living.getAttribute(Attributes.SCALE);
			if (attribute != null) attribute.setBaseValue(scale);
			living.refreshDimensions();
		}
		tint = Looks.tint(spec);
		Looks.after(this, living, spec);
		entity = living;
		Puppets.own(living, this);
		level.addEntity(living);
	}

	private void respawn(Minecraft mc) {
		Puppets.disown(entity);
		create(mc, foot.y());
		apply(true);
	}

	// ---- One tick ----

	private void tick(ShotContext shot) {
		double tNow = ticks * TICK;
		boolean walking = stride != null && !stride.done();
		double travelYaw = Double.NaN;
		if (walking) {
			double s = stride.step(TICK);
			double[] p = stride.path().at(s);
			x = p[0];
			z = p[1];
			// The body follows the direction of travel a little ahead; the head looks further ahead, so it leads turns.
			travelYaw = stride.path().heading(Math.min(stride.path().length(), s + 0.25));
			double speed = stride.speed();
			heading.travel(travelYaw + (strutting() ? strutSway(tNow) : 0), 7 + Math.min(5, speed * 2));
			if (stride.done()) {
				stride = null;
				walking = false;
			}
		}
		boolean recording = shot.recording();
		if (pristine) {
			double g = groundAt(x, z, spawnY, true);
			if (!Double.isNaN(g) && Math.abs(g - foot.y()) > 1e-4) foot.place(g);
		} else {
			foot.step(groundAt(x, z, foot.y(), false), TICK, recording);
		}
		boolean scripted = heading.looking() || heading.turning() || activeHeadGesture();
		life.step(TICK, !scripted, walking);
		double chin = !Double.isNaN(chinOverride) ? chinOverride : (strutting() ? breed.chin() : breed.chin() * 0.3);
		heading.headSpeed(breed.headSpeed() * (temperOf() == Life.Temper.BUSY ? 1.4 : 1));
		double sway = walking ? 0 : life.sway();
		heading.step(TICK, life.yaw() + sway, life.pitch(), chin);
		snapshot();
		apply(false);
		steps(walking);
		for (Prop p : props) p.tick(this);
		gestures.removeIf(g -> g.over(now));
	}

	private Life.Temper temperOf() {
		Life.Temper t = temper(spec);
		return t == null ? breed.temper() : t;
	}

	private boolean strutting() { return stride != null && "strut".equals(gait); }

	/** A strut swings the shoulders: a few degrees of body yaw in time with the stride. */
	private double strutSway(double t) { return 5 * Math.sin(t * Math.PI * 2 * 1.6); }

	private boolean activeHeadGesture() {
		for (Gesture g : gestures) if (!g.kind.arms() && g.weight(now) > 0) return true;
		return false;
	}

	/** Shifts the tick history: what was current becomes the previous tick. */
	private void snapshot() {
		prevX = curX; prevY = curY; prevZ = curZ; prevG = curG;
		prevBody = curBody; prevHead = curHead; prevPitch = curPitch;
		double[] g = gestureHead();
		curX = x; curY = foot.y(); curZ = z; curG = foot.ground();
		curBody = (float) heading.body();
		curHead = (float) (heading.head() + g[0]);
		curPitch = (float) (heading.pitch() + g[1]);
		if (!spawnedOnce) { prevX = curX; prevY = curY; prevZ = curZ; prevG = curG; prevBody = curBody; prevHead = curHead; prevPitch = curPitch; spawnedOnce = true; }
	}

	private boolean spawnedOnce;

	private double[] gestureHead() {
		double yaw = 0, pitch = 0;
		for (Gesture g : gestures) {
			double[] h = g.head(now);
			yaw += h[0];
			pitch += h[1];
		}
		return new double[] {yaw, pitch};
	}

	/** Moves the entity to this tick's state and runs its own tick (its walk cycle and its own animations). */
	private void apply(boolean placed) {
		LivingEntity e = entity;
		if (e == null) return;
		Puppets.ticking = true;
		try {
			if (!placed) e.commonTick();
			e.setPos(curX, curY, curZ);
			e.setYRot(curBody);
			e.setXRot(curPitch);
			e.setOnGround(!foot.air() && !(flapUntil > now));
			e.setDeltaMovement(Vec3.ZERO);
			if (placed) {
				e.setOldPosAndRot();
				e.walkAnimation.stop();
				e.yBodyRotO = curBody;
				e.yHeadRotO = curHead;
			} else {
				e.tick();
			}
			e.setPos(curX, curY, curZ);
			e.setYRot(curBody);
			e.setXRot(curPitch);
			e.yBodyRot = curBody;
			e.yHeadRot = curHead;
			if (placed) { e.yBodyRotO = curBody; e.yHeadRotO = curHead; e.setOldPosAndRot(); }
			e.setOnGround(!foot.air() && !(flapUntil > now));
			e.setDeltaMovement(Vec3.ZERO);
			e.hurtTime = 0;
		} finally {
			Puppets.ticking = false;
		}
	}

	/** Footsteps: the entity's own step sound on the block under it, every 1/0.6 blocks as vanilla counts them. */
	private void steps(boolean walking) {
		LivingEntity e = entity;
		if (e == null || foot.air()) return;
		double moved = Math.hypot(curX - prevX, curZ - prevZ);
		if (moved < 1e-4) return;
		e.moveDist += (float) (moved * 0.6);
		EntityAccess access = (EntityAccess) e;
		if (e.moveDist <= access.videocraft$nextStep()) return;
		BlockPos below = BlockPos.containing(curX, curY - 0.2, curZ);
		BlockState state = e.level().getBlockState(below);
		if (state.isAir()) return;
		access.videocraft$setNextStep(access.videocraft$computeNextStep());
		voice(() -> access.videocraft$playStepSound(below, state));
	}

	/** Runs {@code sound} with this puppet's sounds let through to the client's sound system ({@code PuppetSoundMixin}). */
	void voice(Runnable sound) {
		Puppets.voicing = true;
		try {
			sound.run();
		} finally {
			Puppets.voicing = false;
		}
	}

	/** Plays a sound at the head, through the client's sound system. */
	void play(SoundEvent event, float volume, float pitch) {
		Vec3 h = head();
		entity.level().playLocalSound(h.x, h.y, h.z, event, entity.getSoundSource(), volume, pitch, false);
		heard(event);
	}

	/** Notes a sound the puppet made in the game log (the audio workstream's sounds.csv is the record the mix reads). */
	void heard(SoundEvent event) {
		VideocraftLog.LOGGER.info("VIDEOCRAFT actor {} sound {} at {}s", id, event.location(), String.format(Locale.ROOT, "%.3f", now));
	}

	// ---- Ground ----

	private static double orElse(double v, double fallback) { return Double.isNaN(v) ? fallback : v; }

	/**
	 * The top of the ground under a footprint around (x, z): the highest collision surface within a step's reach above
	 * {@code nearY} and some way below it (a slab, a stair, a fence top, a carpet), sampled at the middle and four
	 * points toward the edges, so a body stands on an edge rather than sinking through it. NaN where there is none.
	 */
	double groundAt(double x, double z, double nearY, boolean placing) {
		if (entity == null) return Double.NaN;
		Level level = entity.level();
		double r = Math.max(0.05, entity.getBbWidth() * 0.32);
		double best = Double.NaN;
		double[][] offsets = {{0, 0}, {r, r}, {-r, r}, {r, -r}, {-r, -r}};
		double up = placing ? 1.6 : 1.3, down = placing ? 6 : 4;
		for (double[] o : offsets) {
			double top = column(level, x + o[0], z + o[1], nearY + up, nearY - down);
			if (!Double.isNaN(top) && (Double.isNaN(best) || top > best)) best = top;
		}
		return best;
	}

	private static double column(Level level, double x, double z, double from, double to) {
		BlockPos.MutableBlockPos pos = new BlockPos.MutableBlockPos();
		int bx = (int) Math.floor(x), bz = (int) Math.floor(z);
		for (int by = (int) Math.floor(from); by >= (int) Math.floor(to); by--) {
			pos.set(bx, by, bz);
			BlockState state = level.getBlockState(pos);
			if (state.isAir()) continue;
			VoxelShape shape = state.getCollisionShape(level, pos);
			if (shape.isEmpty()) continue;
			// Feet go on what is drawn: a fence or a wall collides at 1.5 blocks but is drawn 1 block high.
			double height = shape.max(net.minecraft.core.Direction.Axis.Y);
			VoxelShape drawn = state.getShape(level, pos);
			if (!drawn.isEmpty()) height = Math.min(height, drawn.max(net.minecraft.core.Direction.Axis.Y));
			double top = by + height;
			if (top <= from + 1e-6) return top;
		}
		return Double.NaN;
	}

	// ---- What actions ask of a puppet ----

	/** Walk along {@code points} ({x, z}), starting from where it is. */
	void walk(List<double[]> points, double speed, String gait, double accel, double arrive) {
		pristine = false;
		List<double[]> all = new ArrayList<>();
		all.add(new double[] {x, z});
		all.addAll(points);
		double from = stride != null ? stride.speed() : 0;
		this.gait = gait;
		stride = new Stride(Path.through(all), speed, accel, arrive, from, new Random(random.nextLong()));
	}

	boolean walking() { return stride != null && !stride.done(); }

	void halt(double seconds) { if (stride != null) stride.stop(seconds); }

	void place(Vec3 at, double yaw) {
		pristine = false;
		x = at.x;
		z = at.z;
		stride = null;
		foot.place(orElse(groundAt(x, z, at.y, true), at.y));
		heading.place(yaw);
		spawnedOnce = false;
		snapshot();
		apply(true);
	}

	void turn(double yaw, double pace) { heading.turn(yaw, pace); }

	boolean turning() { return heading.turning(); }

	void look(double yaw, double pitch) { heading.look(yaw, pitch); }

	void lookBack() { heading.look(Double.NaN, 0); }

	void hop(double height, double seconds) { pristine = false; foot.hop(height, seconds); }

	void chin(double degrees) { chinOverride = degrees; }

	double time() { return now; }

	Random random() { return random; }

	Breed breed() { return breed; }

	LivingEntity living() { return entity; }

	Vec3 feet() { return new Vec3(curX, curY, curZ); }

	public int tintColor() { return tint; }

	/** Whether a scripted state is on (sit, sleep, crouch, ...). */
	public boolean has(String state) { return states.contains(state); }

	float phase() { return phase; }

	void gesture(Gesture g) { gestures.add(g); }

	/** The arm pose this frame for a player-shaped body, blended over {@code vanilla}; null when no arm gesture plays. */
	public float[] arms(float[] vanilla) {
		float[] out = null;
		double t = now - (1 - phase) * TICK * 0;
		for (Gesture g : gestures) {
			float[] p = g.arms(t);
			if (p == null) continue;
			if (out == null) out = vanilla.clone();
			Gesture.blend(out, p, (float) g.weight(t));
		}
		return out;
	}

	/** Turns a named state on or off: the entity's own poses where it has them. Throws naming what this entity has. */
	void state(String name, boolean on, String where) {
		LivingEntity e = entity;
		String n = name.toLowerCase(Locale.ROOT);
		switch (n) {
			case "sit" -> {
				if (e instanceof Fox fox) fox.setSitting(on);
				else if (e instanceof TamableAnimal pet) { pet.setInSittingPose(on); pet.setOrderedToSit(on); }
				else if (e instanceof Mannequin) { /* drawn seated by MannequinPoseMixin */ }
				else throw unsupported(n, where);
			}
			case "sleep", "lie" -> {
				if (e instanceof Fox fox) ((FoxAccess) fox).videocraft$setSleeping(on);
				else if (e instanceof Cat cat) cat.setLying(on);
				else if (e instanceof Mannequin m) m.setPose(on ? net.minecraft.world.entity.Pose.SLEEPING : net.minecraft.world.entity.Pose.STANDING);
				else throw unsupported(n, where);
			}
			case "crouch", "sneak", "bow" -> {
				if (e instanceof Fox fox) fox.setIsCrouching(on);
				else if (e instanceof Mannequin m) m.setPose(on ? net.minecraft.world.entity.Pose.CROUCHING : net.minecraft.world.entity.Pose.STANDING);
				else if (e instanceof Goat goat) goat.handleEntityEvent((byte) (on ? 58 : 59));
				else throw unsupported(n, where);
			}
			case "pounce" -> { if (e instanceof Fox fox) fox.setIsPouncing(on); else throw unsupported(n, where); }
			case "tilt", "interested" -> { if (e instanceof Fox fox) fox.setIsInterested(on); else throw unsupported(n, where); }
			case "faceplant" -> { if (e instanceof Fox fox) ((FoxAccess) fox).videocraft$setFaceplanted(on); else throw unsupported(n, where); }
			case "lower", "ram" -> { if (e instanceof Goat goat) goat.handleEntityEvent((byte) (on ? 58 : 59)); else throw unsupported(n, where); }
			case "flap" -> flapUntil = on ? Double.POSITIVE_INFINITY : -1;
			default -> throw unsupported(n, where);
		}
		boolean was = states.contains(n);
		if (on) states.add(n); else states.remove(n);
		if (was != on) {
			String flag = switch (n) { case "sleep", "lie" -> "sleep"; case "crouch", "sneak", "bow" -> "crouch"; default -> n; };
			// How long the body takes to get there: a fox drops onto its haunches quicker than it curls up to sleep.
			double seconds = switch (flag) { case "sit" -> 0.32; case "sleep" -> 0.75; case "crouch" -> 0.16; default -> 0.25; };
			shiftFlag = flag;
			shiftStart = now;
			shiftSeconds = seconds * (0.9 + random.nextDouble() * 0.2);
		}
	}

	private String shiftFlag;
	private double shiftStart, shiftSeconds;

	/** The last change of an on/off pose (sit, sleep, crouch) while it is still easing in, else null. */
	public Shift shift() {
		if (shiftFlag == null || now - shiftStart >= shiftSeconds) return null;
		return new Shift(shiftFlag, Stride.smooth((now - shiftStart) / shiftSeconds));
	}

	/** A change of an on/off pose, for {@link PoseBlend}: which flag, and how far along it is (0 the old pose, 1 the new). */
	public record Shift(String flag, double weight) {}

	/** Flaps (or keeps off the ground) until {@code seconds} from now. */
	void flap(double seconds) {
		flapUntil = now + seconds;
	}

	private IllegalArgumentException unsupported(String state, String where) {
		return new IllegalArgumentException(where + ": " + entityId + " has no state '" + state + "'; states: " + Looks.states(entity));
	}

	void hold(ItemStack stack, boolean offhand) {
		entity.setItemSlot(offhand ? EquipmentSlot.OFFHAND : EquipmentSlot.MAINHAND, stack);
		if (stack.isEmpty()) states.removeIf(s -> s.startsWith("hold")); else states.add("hold");
	}

	/** Drops an item beside the body, the way a chicken lays an egg: it pops out, falls and rests on the ground. */
	void emit(ItemStack stack, Vec3 velocity, double side) {
		double yaw = Math.toRadians(curBody);
		// Behind and a little to one side, at the height of the body.
		double bx = curX + Math.sin(yaw) * 0.25 + Math.cos(yaw) * side, bz = curZ - Math.cos(yaw) * 0.25 + Math.sin(yaw) * side;
		props.add(new Prop(this, stack, new Vec3(bx, curY + entity.getBbHeight() * 0.35, bz), velocity, random.nextFloat()));
	}

	SoundEvent sound(String which, String where) {
		LivingEntity e = entity;
		LivingEntityAccess living = (LivingEntityAccess) e;
		SoundEvent s = switch (which) {
			case "ambient" -> e instanceof Mob ? ((MobAccess) e).videocraft$ambientSound() : null;
			case "hurt" -> living.videocraft$hurtSound(e.damageSources().generic());
			case "death" -> living.videocraft$deathSound();
			case "scream" -> e instanceof Goat ? SoundEvents.GOAT_SCREAMING_AMBIENT : e instanceof Fox ? SoundEvents.FOX_SCREECH : null;
			case "eat" -> e instanceof Fox ? SoundEvents.FOX_EAT : e instanceof Goat goat ? (goat.isScreamingGoat() ? SoundEvents.GOAT_SCREAMING_EAT : SoundEvents.GOAT_EAT) : null;
			case "sleep", "snore" -> e instanceof Fox ? SoundEvents.FOX_SLEEP : null;
			default -> BuiltInRegistries.SOUND_EVENT.getOptional(Identifier.parse(which))
				.orElseThrow(() -> new IllegalArgumentException(where + ": no sound '" + which + "' (ambient, hurt, death, scream, eat, sleep, or a sound id)"));
		};
		if (s == null) throw new IllegalArgumentException(where + ": " + entityId + " has no '" + which + "' sound; give a sound id instead");
		return s;
	}

	float soundVolume() { return ((LivingEntityAccess) entity).videocraft$soundVolume(); }

	/** The state column of actors.csv: the gait while walking (or idle), then any scripted states, joined with '+'. */
	String stateLabel() {
		StringBuilder b = new StringBuilder(walking() ? gait : foot.air() ? "air" : "idle");
		for (String s : states) b.append('+').append(s);
		for (Gesture g : gestures) if (g.weight(now) > 0) b.append('+').append(g.kind.name().toLowerCase(Locale.ROOT));
		return b.toString();
	}

	// ---- Interpolation at the puppet's own fraction of a tick ----

	private double lerp(double a, double b) { return a + (b - a) * phase; }

	private float rotLerp(float a, float b) { return a + (float) Path.wrap(b - a) * phase; }

	/** An item the puppet dropped: it flies, falls, rests, and is ticked with the puppet so its spin is deterministic. */
	static final class Prop {
		private final net.minecraft.world.entity.item.ItemEntity item;
		private Vec3 at, v;
		private boolean resting;

		Prop(Puppet owner, ItemStack stack, Vec3 at, Vec3 v, float bob) {
			net.minecraft.client.multiplayer.ClientLevel level = (net.minecraft.client.multiplayer.ClientLevel) owner.entity.level();
			item = new net.minecraft.world.entity.item.ItemEntity(level, at.x, at.y, at.z, stack);
			item.setId(nextId--);
			item.setNeverPickUp();
			item.setNoGravity(true);
			((io.github.alexandroslekkas.videocraft.mixin.actor.ItemEntityAccess) item).videocraft$setBobOffs(bob * 6.2831855f);
			this.at = at;
			this.v = v;
			Puppets.own(item, owner);
			level.addEntity(item);
		}

		void tick(Puppet owner) {
			Puppets.ticking = true;
			try {
				item.commonTick();
				if (!resting) {
					v = v.add(0, -24 * TICK, 0);
					Vec3 next = at.add(v.scale(TICK));
					double ground = column(item.level(), next.x, next.z, at.y + 0.2, at.y - 6);
					if (!Double.isNaN(ground) && next.y <= ground) {
						next = new Vec3(next.x, ground, next.z);
						v = new Vec3(v.x * 0.4, Math.abs(v.y) > 1.6 ? -v.y * 0.25 : 0, v.z * 0.4);
						if (v.y == 0 && Math.hypot(v.x, v.z) < 0.05) resting = true;
					}
					at = next;
				}
				item.setPos(at.x, at.y, at.z);
				item.setDeltaMovement(Vec3.ZERO);
			} finally {
				Puppets.ticking = false;
			}
		}
	}
}
