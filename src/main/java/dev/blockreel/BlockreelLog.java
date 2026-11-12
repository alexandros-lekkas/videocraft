package dev.blockreel;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/** The one logger. Lines the CLI reads start with {@code BLOCKREEL }; never log tokens or private paths of other apps. */
public final class BlockreelLog {
	public static final Logger LOGGER = LoggerFactory.getLogger("blockreel");

	private BlockreelLog() {}
}
