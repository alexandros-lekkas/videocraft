package io.github.alexandroslekkas.videocraft;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/** The one logger. Lines the CLI reads start with {@code VIDEOCRAFT }; never log tokens or private paths of other apps. */
public final class VideocraftLog {
	public static final Logger LOGGER = LoggerFactory.getLogger("videocraft");

	private VideocraftLog() {}
}
