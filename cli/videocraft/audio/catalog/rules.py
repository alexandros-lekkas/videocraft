"""How the catalog tags a Minecraft sound event: rules on the event id (its family, mob, material and action) plus a
hand-curated list of meanings that matter to comedy video (pop, plop, ding, boing, whoosh, impact, fail…), and which
original library sound stands in for it in an original-only export. Used only by `audio catalog --refresh`
(build.py); the result is committed in minecraft.toml, so nothing at run time needs these rules or the game assets.
"""
import fnmatch

# Entities that are not creatures (no voice, no mob tag).
NOT_MOBS = {'arrow', 'boat', 'generic', 'item', 'item_frame', 'glow_item_frame', 'painting', 'minecart', 'firework_rocket',
            'lightning_bolt', 'experience_orb', 'experience_bottle', 'egg', 'ender_eye', 'ender_pearl', 'snowball', 'fishing_bobber',
            'splash_potion', 'lingering_potion', 'dragon_fireball', 'evoker_fangs', 'shulker_bullet', 'tnt', 'armor_stand',
            'wind_charge', 'leash_knot', 'cushion', 'hostile', 'fish'}
HOSTILE = {'zombie', 'skeleton', 'creeper', 'spider', 'enderman', 'witch', 'blaze', 'ghast', 'slime', 'magma_cube', 'phantom',
           'drowned', 'husk', 'stray', 'wither', 'wither_skeleton', 'guardian', 'elder_guardian', 'shulker', 'vindicator', 'evoker',
           'pillager', 'ravager', 'vex', 'illusioner', 'hoglin', 'zoglin', 'piglin_brute', 'warden', 'silverfish', 'endermite',
           'breeze', 'bogged', 'creaking', 'ender_dragon', 'zombie_villager', 'zombified_piglin', 'parched', 'zombie_nautilus',
           'camel_husk', 'zombie_horse', 'skeleton_horse', 'hostile'}
# Variants of a mob that answer to its name too.
MOB_BASE = {'baby_cat': 'cat', 'cat_royal': 'cat', 'baby_chicken': 'chicken', 'chicken_picky': 'chicken', 'baby_horse': 'horse',
            'baby_pig': 'pig', 'pig_big': 'pig', 'pig_mini': 'pig', 'baby_wolf': 'wolf', 'wolf_angry': 'wolf', 'wolf_big': 'wolf',
            'wolf_cute': 'wolf', 'wolf_grumpy': 'wolf', 'wolf_puglin': 'wolf', 'wolf_sad': 'wolf', 'cow_moody': 'cow',
            'baby_nautilus': 'nautilus', 'copper_golem_oxidized': 'copper_golem', 'copper_golem_weathered': 'copper_golem',
            'copper_golem_become_statue': 'copper_golem', 'camel_husk': 'camel', 'zombie_villager': 'zombie',
            'zombified_piglin': 'piglin', 'piglin_brute': 'piglin', 'wither_skeleton': 'skeleton', 'skeleton_horse': 'horse',
            'zombie_horse': 'horse', 'elder_guardian': 'guardian', 'glow_squid': 'squid', 'mooshroom': 'cow',
            'wandering_trader': 'villager', 'happy_ghast': 'ghast', 'ghastling': 'ghast', 'baby_ghast': 'ghast',
            'tropical_fish': 'fish', 'puffer_fish': 'fish', 'cod': 'fish', 'salmon': 'fish', 'small_sulfur_cube': 'sulfur_cube'}
BABY = {'baby_cat', 'baby_chicken', 'baby_horse', 'baby_pig', 'baby_wolf', 'baby_nautilus', 'ghastling', 'tadpole'}
# Plain words a person searches with, by mob.
MOB_WORDS = {'goat': ['goat'], 'sheep': ['sheep'], 'chicken': ['chicken', 'bird'], 'parrot': ['parrot', 'bird'], 'fox': ['fox'],
             'wolf': ['wolf', 'dog'], 'cat': ['cat'], 'ocelot': ['cat'], 'cow': ['cow'], 'pig': ['pig'], 'villager': ['villager', 'people'],
             'pillager': ['people'], 'vindicator': ['people'], 'witch': ['people'], 'evoker': ['people'], 'illusioner': ['people'],
             'bee': ['bee', 'insect'], 'bat': ['bat'], 'horse': ['horse'], 'donkey': ['horse', 'donkey'], 'mule': ['horse'],
             'llama': ['llama'], 'camel': ['camel'], 'frog': ['frog'], 'rabbit': ['rabbit'], 'panda': ['panda'], 'polar_bear': ['bear']}

# The action at the end of an id -> tags (and whether it is a voice).
ACTIONS = {
    'ambient': ('ambient',), 'idle': ('ambient',), 'idle_air': ('ambient',), 'idle_ground': ('ambient',), 'idle_water': ('ambient',),
    'ambient_land': ('ambient',), 'ambient_water': ('ambient',), 'ambient_baby': ('ambient', 'baby'), 'stray_ambient': ('ambient',),
    'ambient_with_item': ('ambient',), 'ambient_without_item': ('ambient',), 'aggressive_ambient': ('ambient', 'angry'),
    'worried_ambient': ('ambient', 'sad', 'worried'),
    'hurt': ('hurt',), 'hurt_land': ('hurt',), 'hurt_water': ('hurt',), 'hurt_small': ('hurt', 'small'), 'hurt_closed': ('hurt',),
    'hurt_baby': ('hurt', 'baby'), 'hurt_drown': ('hurt', 'water'), 'hurt_freeze': ('hurt', 'cold'), 'hurt_on_fire': ('hurt', 'fire'),
    'hurt_sweet_berry_bush': ('hurt', 'ouch'), 'hurt_reduced': ('hurt',), 'damage': ('hurt',),
    'death': ('death',), 'death_land': ('death',), 'death_water': ('death',), 'death_small': ('death', 'small'), 'death_baby': ('death', 'baby'),
    'angry': ('angry',), 'aggro': ('angry',), 'growl': ('angry', 'growl'), 'hiss': ('angry', 'hiss'), 'roar': ('angry', 'roar', 'big'),
    'warning': ('angry', 'warning'), 'warn': ('angry', 'warning'), 'agitated': ('angry',), 'listening_angry': ('angry',),
    'stare': ('angry', 'spooky'), 'prepare_ram': ('angry',), 'screech': ('angry', 'scream'), 'jealous': ('angry',),
    'happy': ('happy',), 'purr': ('happy', 'purr'), 'purreow': ('happy',), 'celebrate': ('happy', 'celebrate', 'cheer', 'crowd'),
    'admiring_item': ('happy',), 'play': ('happy',), 'pant': ('happy', 'pant'),
    'whine': ('sad', 'whine'), 'cant_breed': ('sad',), 'beg_for_food': ('beg', 'cute'),
    'yes': ('yes', 'agree'), 'no': ('no', 'disagree', 'fail'), 'trade': ('trade', 'hmm'),
    'scream': ('scream',), 'sneeze': ('sneeze', 'comedy'), 'pre_sneeze': ('sneeze',), 'burp': ('burp', 'comedy'),
    'eat': ('eat', 'eating'), 'drink': ('drink', 'gulp'), 'step': ('footstep', 'step'), 'step_sand': ('footstep', 'step', 'sand'),
    'step_wood': ('footstep', 'step', 'wood'), 'step_water': ('footstep', 'step', 'water'), 'step_lava': ('footstep', 'step', 'lava'),
    'gallop': ('footstep', 'gallop'), 'gallop_water': ('footstep', 'gallop', 'water'), 'shamble': ('footstep', 'step'),
    'shamble_baby': ('footstep', 'step', 'baby'),
    'jump': ('jump',), 'jump_small': ('jump', 'small'), 'jump_water': ('jump', 'water'), 'long_jump': ('jump',), 'land': ('land', 'thud'),
    'attack': ('attack',), 'bite': ('attack', 'bite'), 'shoot': ('shoot',), 'spit': ('spit', 'comedy'), 'sting': ('attack', 'sting'),
    'flap': ('flap', 'wings'), 'fly': ('flap', 'wings'), 'swim': ('swim', 'water'), 'splash': ('splash', 'water'), 'flop': ('flop', 'fish'),
    'milk': ('milk',), 'shear': ('snip',), 'teleport': ('teleport',), 'squish': ('squish', 'splat'), 'squish_small': ('squish', 'splat', 'small'),
    'break': ('break',), 'place': ('place',), 'hit': ('hit',), 'fall': ('fall',), 'open': ('open',), 'close': ('close',),
    'click_on': ('click',), 'click_off': ('click',), 'click': ('click',), 'use': ('use',), 'throw': ('throw', 'whoosh'),
    'spawn': ('spawn',), 'loop': ('loop',), 'convert': ('convert',), 'sniff': ('sniff',), 'sleep': ('sleep', 'snore'),
    'dig': ('dig',), 'emerge': ('emerge', 'rumble'), 'heartbeat': ('heartbeat', 'spooky'), 'tendril_clicks': ('click', 'spooky'),
}
VOICE_TAGS = {'ambient', 'hurt', 'death', 'angry', 'happy', 'sad', 'scream', 'yes', 'no', 'trade', 'celebrate', 'growl', 'sneeze',
              'whine', 'purr', 'beg', 'roar', 'hiss', 'pant', 'burp', 'sniff', 'snore'}

# Block materials -> the surface a footstep is on.
SURFACES = {
    'wood': ['wood', 'cherry_wood', 'bamboo_wood', 'nether_wood', 'ladder', 'scaffolding', '*_hanging_sign', 'hanging_sign', 'bamboo',
             'chiseled_bookshelf', 'shelf'],
    'stone': ['stone', 'deepslate*', 'tuff*', 'polished_*', 'calcite', 'basalt', 'nether_bricks', 'netherrack', 'dripstone_block',
              'pointed_dripstone', 'mud_bricks', 'bone_block', 'lodestone', 'gilded_blackstone', 'ancient_debris', 'nether_ore',
              'nether_gold_ore', 'resin_bricks', 'cinnabar', 'sulfur', 'sulfur_spike', 'potent_sulfur', 'decorated_pot', 'spawner'],
    'grass': ['grass', 'wet_grass', 'moss', 'moss_carpet', 'azalea', 'flowering_azalea', 'roots', 'hanging_roots', 'vine', 'cave_vines',
              'big_dripleaf', 'small_dripleaf', 'nether_sprouts', 'fungus', 'spore_blossom', 'pink_petals', 'rooted_dirt',
              'mangrove_roots', 'muddy_mangrove_roots', 'shroomlight', 'wart_block', 'stem', 'weeping_vines', 'nylium', 'cherry_sapling',
              'shelf_mushroom', 'sculk', 'sculk_vein', 'sculk_catalyst', 'sculk_sensor', 'sculk_shrieker', 'crop', 'sweet_berry_bush'],
    'leaves': ['*_leaves', 'leaf_litter'],
    'sand': ['sand', 'suspicious_sand', 'soul_sand', 'soul_soil'],
    'gravel': ['gravel', 'suspicious_gravel'],
    'snow': ['snow', 'powder_snow'],
    'wool': ['wool', 'straw_bed', 'moss_carpet'],
    'metal': ['metal', 'iron', 'copper', 'copper_*', 'chain', 'lantern', 'anvil', 'netherite_block', 'heavy_core', 'trial_spawner',
              'vault', 'iron_door', 'iron_trapdoor'],
    'glass': ['glass', 'amethyst_*', '*_amethyst_bud'],
    'mud': ['mud', 'packed_mud', 'frogspawn'],
    'slime': ['slime_block', 'honey_block'],
    'coral': ['coral_block'],
}

# Curated meanings, by id pattern (fnmatch on the id without "minecraft:"). Every matching rule adds its tags.
MEANINGS = [
    (['ui.button.click', '*_button.click_*', 'block.lever.click', 'block.tripwire.click_*', 'block.comparator.click', '*pressure_plate.click_*'],
     ['click', 'ui', 'switch']),
    (['ui.*'], ['ui']),
    (['ui.toast.in', 'ui.toast.out'], ['whoosh', 'swish', 'notification']),
    (['ui.toast.challenge_complete'], ['success', 'fanfare', 'achievement', 'win', 'ding']),
    (['ui.hud.bubble_pop', 'block.bubble_column.bubble_pop', 'block.lava.pop'], ['pop', 'bubble']),
    (['entity.item.pickup'], ['pop', 'pickup', 'collect', 'comedy']),
    (['entity.experience_orb.pickup'], ['ding', 'xp', 'pickup', 'collect', 'coin', 'cash']),
    (['entity.player.levelup'], ['ding', 'levelup', 'level', 'xp', 'success', 'win']),
    (['entity.arrow.hit_player'], ['ding', 'hit']),
    (['entity.chicken.egg', 'block.sniffer_egg.plop', 'entity.turtle.lay_egg', 'entity.frog.lay_spawn'], ['plop', 'egg', 'lay', 'drop', 'comedy']),
    (['block.bell.use', 'block.bell.resonate'], ['bell', 'ding', 'alarm']),
    (['block.amethyst_block.chime', 'block.amethyst_block.resonate', 'entity.firework_rocket.twinkle*', 'block.note_block.chime'],
     ['sparkle', 'chime', 'twinkle', 'magic']),
    (['block.enchantment_table.use', 'entity.evoker.cast_spell', 'entity.illusioner.cast_spell', 'entity.evoker.prepare_*',
      'entity.illusioner.prepare_*', 'block.beacon.power_select', 'item.totem.use', 'block.respawn_anchor.charge'], ['magic', 'spell', 'sparkle']),
    (['entity.enderman.teleport', 'item.chorus_fruit.teleport', 'entity.shulker.teleport', 'entity.fox.teleport', 'entity.player.teleport',
      'block.portal.trigger', 'block.portal.travel', 'entity.wandering_trader.disappeared', 'entity.wandering_trader.reappeared'],
     ['teleport', 'warp', 'magic', 'vanish']),
    (['entity.player.attack.sweep', 'entity.player.attack.nodamage', 'entity.player.attack.weak', 'entity.fishing_bobber.throw',
      'item.spear*.lunge_*', 'item.spear*.use'], ['swish', 'swing', 'whoosh', 'attack']),
    (['entity.ender_pearl.throw', 'entity.snowball.throw', 'entity.egg.throw', 'entity.wind_charge.throw', 'item.trident.throw',
      'entity.breeze.wind_burst', 'entity.wind_charge.wind_burst', 'entity.breeze.whirl', 'entity.phantom.swoop', 'item.elytra.flying',
      'entity.bat.takeoff', 'entity.player.attack.sweep', 'item.trident.riptide_*', 'item.mace.smash_air', 'entity.breeze.charge'],
     ['whoosh', 'air', 'fast']),
    (['block.anvil.land', 'block.anvil.destroy', 'entity.goat.ram_impact', 'entity.goat.screaming.ram_impact', 'item.mace.smash_ground*',
      'entity.iron_golem.attack', 'entity.player.big_fall', 'entity.generic.big_fall', 'entity.hostile.big_fall', 'entity.player.attack.strong',
      'entity.player.attack.crit', 'entity.player.attack.knockback', 'entity.zombie.attack_wooden_door', 'entity.zombie.attack_iron_door',
      'entity.zombie.break_wooden_door', 'entity.warden.attack_impact', 'item.trident.hit_ground', 'item.shield.block', 'entity.ravager.attack'],
     ['impact', 'hit', 'bang', 'bonk']),
    (['block.anvil.*'], ['anvil', 'clang']),
    (['entity.generic.small_fall', 'entity.player.small_fall', 'entity.hostile.small_fall', 'entity.armor_stand.fall', '*.land',
      'block.pointed_dripstone.land'], ['thud', 'land', 'fall']),
    (['entity.generic.explode', 'entity.dragon_fireball.explode', 'entity.firework_rocket.large_blast*', 'entity.firework_rocket.blast*',
      'entity.lightning_bolt.impact', 'entity.wither.break_block', 'entity.warden.sonic_boom'], ['explosion', 'boom', 'blast', 'impact']),
    (['entity.creeper.primed', 'entity.tnt.primed'], ['fuse', 'hiss', 'tension', 'comedy']),
    (['entity.lightning_bolt.thunder', 'weather.*'], ['thunder', 'weather', 'rumble']),
    (['weather.rain*'], ['rain', 'water']),
    (['*_door.open', '*_door.close', '*_trapdoor.open', '*_trapdoor.close', '*fence_gate.open', '*fence_gate.close', 'block.fence_gate.*'],
     ['door']),
    (['block.chest.*', 'block.ender_chest.*', 'block.copper_chest*', 'block.barrel.*', 'block.shulker_box.*'], ['chest', 'container']),
    (['block.chest.locked', 'block.crafter.fail', 'block.dispenser.fail', 'item.bundle.insert_fail', 'block.decorated_pot.insert_fail',
      'block.vault.insert_item_fail', 'block.vault.reject_rewarded_player', '*.waxed_interact_fail', 'entity.villager.no',
      'entity.wandering_trader.no'], ['fail', 'error', 'denied']),
    (['entity.item.break', 'item.shield.break', 'item.wolf_armor.break', 'block.redstone_torch.burnout', 'item.lead.break'],
     ['fail', 'break', 'snap']),
    (['block.fire.extinguish', 'block.lava.extinguish', 'entity.generic.extinguish_fire', 'block.candle.extinguish'],
     ['fizzle', 'fail', 'hiss', 'steam']),
    (['block.note_block.*'], ['note', 'instrument', 'music']),
    (['block.note_block.basedrum', 'block.note_block.snare', 'block.note_block.hat'], ['drum', 'percussion', 'beat']),
    (['block.note_block.snare'], ['snare', 'drumroll']),
    (['block.note_block.didgeridoo', 'block.note_block.bass'], ['fail', 'low', 'dun']),
    (['block.note_block.bell', 'block.note_block.chime', 'block.note_block.pling', 'block.note_block.xylophone', 'block.note_block.iron_xylophone',
      'block.note_block.cow_bell'], ['ding', 'chime']),
    (['block.note_block.imitate.*', 'entity.parrot.imitate.*'], ['imitate']),
    (['entity.generic.eat', 'entity.*.eat', 'entity.player.burp', 'entity.goat.screaming.eat'], ['eating', 'munch']),
    (['entity.generic.drink', 'item.honey_bottle.drink', 'entity.witch.drink', 'entity.wandering_trader.drink_*'], ['drink', 'gulp']),
    (['entity.generic.splash', 'entity.player.splash*', 'entity.hostile.splash', 'entity.fishing_bobber.splash', '*.splash',
      'item.bucket.empty*', 'ambient.underwater.enter'], ['splash', 'water']),
    (['entity.generic.swim', 'entity.player.swim', 'entity.hostile.swim', 'ambient.underwater.*', 'block.bubble_column.*',
      'block.water.ambient', 'item.bucket.fill*', 'item.bottle.fill'], ['water']),
    (['block.bubble_column.*', 'ambient.underwater.loop.additions*', 'entity.puffer_fish.blow_*'], ['bubble']),
    (['entity.puffer_fish.blow_up'], ['inflate', 'comedy']), (['entity.puffer_fish.blow_out'], ['deflate', 'comedy']),
    (['item.goat_horn.sound.*', 'event.raid.horn'], ['horn', 'honk', 'alarm']),
    (['entity.goat.screaming.*'], ['scream', 'goat', 'comedy']),
    (['entity.enderman.scream', 'entity.ghast.scream', 'entity.fox.screech', 'entity.warden.roar', 'block.sculk_shrieker.shriek'],
     ['scream']),
    (['entity.villager.celebrate', 'entity.pillager.celebrate', 'entity.vindicator.celebrate', 'entity.witch.celebrate', 'entity.evoker.celebrate',
      'entity.piglin.celebrate', 'entity.ravager.celebrate'], ['crowd', 'cheer', 'celebrate', 'applause']),
    (['entity.villager.ambient', 'entity.villager.trade', 'entity.wandering_trader.ambient', 'entity.wandering_trader.trade'], ['hmm', 'murmur']),
    (['entity.villager.yes', 'entity.wandering_trader.yes'], ['yes', 'agree', 'success']),
    (['entity.villager.work_*'], ['work', 'tool']),
    (['ambient.cave', 'ambient.*.mood', 'entity.warden.heartbeat', 'entity.warden.nearby_*', 'entity.elder_guardian.curse',
      'event.mob_effect.*', 'block.sculk_shrieker.shriek', 'entity.warden.listening', 'block.trial_spawner.ominous_activate',
      'block.creaking_heart.*', 'entity.creaking.*'], ['spooky', 'creepy', 'tension']),
    (['entity.elder_guardian.curse', 'event.mob_effect.bad_omen', 'event.mob_effect.raid_omen', 'event.mob_effect.trial_omen',
      'entity.wither.spawn', 'entity.ender_dragon.growl', 'block.end_portal.spawn', 'block.end_gateway.spawn', 'event.raid.horn',
      'item.totem.use', 'ambient.cave', 'block.trial_spawner.ominous_activate', 'entity.warden.emerge', 'entity.ender_dragon.death',
      'entity.wither.death'], ['sting', 'dramatic', 'reveal']),
    (['block.grindstone.use', 'item.brush.brushing.*', 'item.axe.scrape', 'item.axe.strip', 'item.axe.wax_off', 'item.shovel.flatten',
      'item.hoe.till', 'block.honey_block.slide', 'entity.breeze.slide'], ['scrape', 'scratch']),
    (['block.honey_block.slide', 'entity.breeze.slide'], ['slide']),
    (['block.piston.*', 'block.dispenser.*', 'block.crafter.craft', 'item.crossbow.loading_*', 'item.crossbow.quick_charge_*',
      'block.vault.*_shutter', 'block.trial_spawner.*_shutter'], ['mechanical', 'machine']),
    (['item.book.*', 'ui.cartography_table.take_result', 'ui.loom.*', 'block.chiseled_bookshelf.*'], ['paper', 'book']),
    (['block.glass.break', 'block.decorated_pot.shatter', 'entity.splash_potion.break', 'block.amethyst_cluster.break'],
     ['glass', 'crash', 'shatter', 'break']),
    (['block.fire.ambient', 'item.flintandsteel.use', 'item.firecharge.use', 'block.campfire.crackle', 'block.*furnace.fire_crackle',
      'entity.blaze.burn', 'entity.generic.burn', 'block.blastfurnace.fire_crackle', 'block.smoker.smoke'], ['fire', 'crackle']),
    (['entity.arrow.shoot', 'item.crossbow.shoot', 'entity.skeleton.shoot', 'entity.stray.shoot'], ['shoot', 'twang', 'bow']),
    (['entity.slime.jump*', 'entity.magma_cube.jump', 'block.shelf_mushroom.bounce', 'entity.sulfur_cube.bounce', 'entity.small_sulfur_cube.jump',
      'entity.sulfur_cube.jump', 'block.slime_block.fall', 'block.slime_block.step', 'entity.rabbit.jump'], ['boing', 'bounce', 'spring']),
    (['entity.slime.squish*', 'entity.magma_cube.squish*', 'block.slime_block.*', 'block.honey_block.*', 'block.mud.*', 'entity.sulfur_cube.squish',
      'entity.small_sulfur_cube.squish'], ['splat', 'squish', 'wet']),
    (['entity.bat.ambient', 'entity.rabbit.ambient', 'entity.silverfish.ambient', 'entity.endermite.ambient', 'entity.bat.hurt',
      'entity.allay.*', 'entity.armadillo.ambient', 'entity.dolphin.play'], ['squeak', 'small']),
    (['entity.bee.loop', 'entity.bee.loop_aggressive', 'block.beehive.work'], ['buzz', 'insect']),
    (['entity.cat.hiss', 'entity.baby_cat.hiss', 'entity.cat_royal.hiss'], ['hiss']),
    (['entity.panda.sneeze', 'entity.panda.pre_sneeze'], ['sneeze']),
    (['entity.player.hurt*', 'entity.player.death'], ['ouch', 'player']),
    (['entity.player.*', 'item.*'], ['player']),
    (['music.*', 'music_disc.*'], ['music']),
    (['music_disc.*'], ['record', 'disc']),
    (['ambient.*', 'block.*.ambient', 'block.*.idle', '*.loop', 'block.water.ambient', 'block.lava.ambient'], ['ambience']),
    (['entity.experience_orb.pickup', 'ui.stonecutter.take_result', 'ui.loom.take_result', 'ui.cartography_table.take_result'],
     ['reward', 'collect']),
    (['entity.player.levelup', 'ui.toast.challenge_complete', 'entity.villager.yes', 'entity.experience_orb.pickup'], ['correct']),
    (['entity.zombie.ambient', 'entity.husk.ambient', 'entity.drowned.ambient*', 'entity.zombie_villager.ambient', 'entity.zombified_piglin.ambient',
      'entity.piglin.ambient', 'entity.hoglin.ambient', 'entity.ravager.ambient'], ['grunt', 'monster']),
    (['entity.goat.ambient', 'entity.goat.hurt', 'entity.goat.death', 'entity.sheep.ambient', 'entity.sheep.hurt', 'entity.sheep.death',
      'entity.goat.screaming.ambient'], ['bleat']),
    (['entity.chicken.ambient', 'entity.chicken.hurt', 'entity.chicken.death', 'entity.baby_chicken.ambient', 'entity.chicken_picky.ambient'],
     ['cluck']),
    (['entity.cow.ambient', 'entity.cow_moody.ambient', 'entity.mooshroom.*'], ['moo']),
    (['entity.pig.ambient', 'entity.pig_big.ambient', 'entity.pig_mini.ambient', 'entity.baby_pig.ambient'], ['oink']),
    (['entity.cat.ambient', 'entity.cat.stray_ambient', 'entity.baby_cat.ambient', 'entity.cat_royal.ambient', 'entity.ocelot.ambient',
      'entity.cat.purreow'], ['meow']),
    (['entity.wolf*.ambient', 'entity.baby_wolf.ambient', 'entity.wolf*.growl'], ['woof', 'bark']),
    (['entity.fox.ambient', 'entity.fox.aggro', 'entity.fox.screech'], ['yip', 'bark']),
]

# The original stand-in for an event, by pattern, checked before the tag match (first match wins). "" = none.
ORIGINAL = [
    ('block.note_block.*', ''),  # the mix plays a tone at the logged pitch instead (sfx.py), better than any one sample
    ('entity.goat.screaming.*', 'scream'), ('entity.goat.*.step', 'footstep-grass'),
    ('*.step', None), ('*.gallop', 'footstep-wood'),
    ('entity.goat.ambient', 'bleat'), ('entity.goat.hurt', 'yelp'), ('entity.goat.death', 'bleat'), ('entity.sheep.*', 'bleat'),
    ('entity.chicken.egg', 'plop'), ('entity.chicken*.*', 'cluck'), ('entity.baby_chicken.*', 'cluck'), ('entity.parrot.ambient', 'cluck'),
    ('entity.fox.sleep', 'hmm'), ('entity.fox.*', 'yip'), ('entity.wolf*.*', 'woof'), ('entity.baby_wolf.*', 'woof'),
    ('entity.cat*.hiss', 'hiss'), ('entity.cat*.*', 'meow'), ('entity.baby_cat.*', 'meow'), ('entity.ocelot.*', 'meow'),
    ('entity.cow*.*', 'moo'), ('entity.mooshroom.*', 'moo'), ('entity.pig*.*', 'oink'), ('entity.baby_pig.*', 'oink'),
    ('entity.villager.celebrate', 'cheer'), ('entity.villager.yes', 'success-chime'), ('entity.villager.no', 'error-buzz'),
    ('entity.villager.*', 'hmm'), ('entity.wandering_trader.*', 'hmm'),
    ('entity.zombie*.*', 'grunt'), ('entity.husk.*', 'grunt'), ('entity.drowned.*', 'grunt'), ('entity.piglin*.*', 'grunt'),
    ('entity.player.hurt*', 'yelp'), ('entity.player.levelup', 'level-up'), ('entity.experience_orb.pickup', 'ding'),
    ('entity.player.burp', 'gulp'), ('entity.generic.eat', 'munch'),
    ('block.glass.break', 'shatter'), ('block.decorated_pot.shatter', 'shatter'), ('entity.splash_potion.break', 'shatter'),
    ('block.*glass*.break', 'shatter'), ('block.*.break', 'thud'), ('block.*.place', 'thud'), ('block.*.hit', 'click-soft'), ('block.*.fall', 'thud'),
]

# Tags that say too little to choose a stand-in on their own.
WEAK = {'ambient', 'voice', 'mob', 'animal', 'comedy', 'cartoon', 'small', 'big', 'player', 'entity', 'block', 'item', 'use', 'hit',
        'loop', 'ambience', 'music', 'people', 'baby', 'open', 'close', 'water', 'low'}


def matches(name, patterns):
    return any(fnmatch.fnmatchcase(name, p) for p in patterns)


def surface_of(material):
    for surface, patterns in SURFACES.items():
        if matches(material, patterns):
            return surface
    return None


def category_of(name):
    """The sound category the game usually plays an event in, from its id (sounds.json does not say)."""
    head, _, rest = name.partition('.')
    if head == 'entity':
        mob = rest.split('.', 1)[0]
        if mob == 'player':
            return 'player'
        return 'hostile' if mob in HOSTILE else 'neutral'
    return {'block': 'block', 'item': 'player', 'ambient': 'ambient', 'music': 'music', 'music_disc': 'record', 'ui': 'master',
            'weather': 'weather', 'event': 'master', 'enchant': 'player', 'particle': 'block'}.get(head, 'master')


def tags_for(name):
    """The tags of a sound event id (no namespace), as a sorted list."""
    parts = name.split('.')
    tags = {parts[0]}
    action = None
    if parts[0] == 'entity' and len(parts) > 1:
        mob = parts[1]
        rest = parts[2:]
        if mob not in NOT_MOBS:
            base = MOB_BASE.get(mob, mob)
            tags |= {mob, base, 'mob'} | set(MOB_WORDS.get(base, ()))
            if mob in BABY:
                tags.add('baby')
            if mob in HOSTILE:
                tags.add('monster')
        else:
            tags.add(mob)
        action = '.'.join(rest)
        if rest and rest[0] == 'screaming':
            tags.add('scream')
            action = '.'.join(rest[1:])
        for a in (action, rest[-1] if rest else ''):
            if a in ACTIONS:
                tags |= set(ACTIONS[a])
                break
        if mob not in NOT_MOBS and tags & VOICE_TAGS:
            tags.add('voice')
        if 'footstep' in tags and mob not in NOT_MOBS:
            tags.add('mob-step')
    elif parts[0] == 'block' and len(parts) > 1:
        material = parts[1]
        action = '.'.join(parts[2:])
        tags.add(material)
        surface = surface_of(material)
        if surface:
            tags.add(surface)
        last = parts[-1] if len(parts) > 2 else ''
        if last in ACTIONS:
            tags |= set(ACTIONS[last])
        if last == 'step':
            tags.add('footstep')
            if surface:
                tags.add(f'footstep-{surface}')
    elif parts[0] == 'item' and len(parts) > 1:
        tags.add(parts[1])
        last = parts[-1]
        if last in ACTIONS:
            tags |= set(ACTIONS[last])
    else:
        tags |= set(p for p in parts[1:] if p.isalpha() and len(p) > 2)
    for patterns, extra in MEANINGS:
        if matches(name, patterns):
            tags |= set(extra)
    return sorted(tags)


def original_for(name, tags, library_index):
    """The library sound that stands in for this event in an original-only export, or None."""
    for pattern, lib in ORIGINAL:
        if fnmatch.fnmatchcase(name, pattern):
            if lib is None:
                break
            return lib or None
    if 'footstep' in tags:
        for surface in ('wood', 'stone', 'grass', 'sand', 'snow', 'metal'):
            if surface in tags:
                return f'footstep-{surface}'
        for near, lib in (('gravel', 'footstep-sand'), ('wool', 'footstep-snow'), ('leaves', 'footstep-grass'), ('mud', 'footstep-sand'),
                          ('glass', 'footstep-stone'), ('slime', 'footstep-grass'), ('coral', 'footstep-stone')):
            if near in tags:
                return lib
        return 'footstep-grass'
    strong = [t for t in tags if t not in WEAK]
    best, best_score = None, 0.0
    for lib, entry in library_index.items():
        have = set(entry.get('tags', ())) | {lib}
        score = sum(1.0 for t in strong if t in have) + (1.5 if lib in strong else 0.0) + 0.1 * sum(1 for t in tags if t in WEAK and t in have)
        if score > best_score or (score == best_score and best is not None and lib < best):
            best, best_score = lib, score
    return best if best_score >= 1.5 else None
