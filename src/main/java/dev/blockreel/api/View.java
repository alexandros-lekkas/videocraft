package dev.blockreel.api;

/**
 * Who holds the camera.
 * <ul>
 * <li>{@code CAMERA}: an unseen operator. The camera entity is an invisible marker; the player is a spectator parked
 * nearby (vanilla does not draw the local player when the camera is another entity) and no HUD is drawn.</li>
 * <li>{@code THIRD}: the player filmed. The player stays the camera entity, in third person, and the rig moves the
 * camera (CameraMixin). View bobbing is off, or the game would bob the filmed view.</li>
 * <li>{@code FIRST}: the player's own eyes. The rig returns no pose; the actor's hand turns the view.</li>
 * </ul>
 */
public enum View { CAMERA, THIRD, FIRST }
