// The trailer's motion graphics: one frame at a time from a timeline (runs/trailer/timeline-<layout>.json, written by
// trailer/make.py), drawn with CoreGraphics and CoreText (vector, antialiased text in the system's SF Pro and SF
// Mono), footage decoded by ffmpeg into the same frame. Output: raw BGRA frames on stdout, or PNG stills.
//
//   swiftc -O trailer/render.swift -o runs/trailer/bin/render
//   render <timeline.json> [--from F] [--to F]            raw frames F..<T to stdout (pipe to ffmpeg)
//   render <timeline.json> --png <dir> --at F1,F2,...     PNG stills of those frames
//
// Every scene is a function of absolute time, so any frame renders alone (stills, strips, the poster).
import AppKit
import CoreGraphics
import CoreText
import Foundation
import ImageIO
import UniformTypeIdentifiers

// MARK: - input

let argv = CommandLine.arguments
guard argv.count >= 2, let raw = FileManager.default.contents(atPath: argv[1]),
	let J = try? JSONSerialization.jsonObject(with: raw) as? [String: Any] else {
	FileHandle.standardError.write("usage: render <timeline.json> [--from F --to T | --png DIR --at F,...]\n".data(using: .utf8)!)
	exit(2)
}
func arg(_ name: String) -> String? {
	if let i = argv.firstIndex(of: name), i + 1 < argv.count { return argv[i + 1] }
	return nil
}

let W = J["width"] as! Int, H = J["height"] as! Int
let FPS = (J["fps"] as? Double) ?? 60
let FRAMES = J["frames"] as! Int
let V = H > W  // the vertical layout
let CW = CGFloat(W), CH = CGFloat(H)
let FFMPEG = (J["ffmpeg"] as? String) ?? "/opt/homebrew/bin/ffmpeg"

// MARK: - colour

func hex(_ s: String, _ a: CGFloat = 1) -> CGColor {
	var v: UInt64 = 0
	Scanner(string: String(s.dropFirst())).scanHexInt64(&v)
	return CGColor(srgbRed: CGFloat((v >> 16) & 255) / 255, green: CGFloat((v >> 8) & 255) / 255,
		blue: CGFloat(v & 255) / 255, alpha: a)
}
let palette = J["colors"] as! [String: String]
func C(_ name: String, _ a: CGFloat = 1) -> CGColor { hex(palette[name] ?? name, a) }
func mix(_ a: CGColor, _ b: CGColor, _ t: CGFloat) -> CGColor {
	let x = a.components!, y = b.components!
	return CGColor(srgbRed: x[0] + (y[0] - x[0]) * t, green: x[1] + (y[1] - x[1]) * t, blue: x[2] + (y[2] - x[2]) * t,
		alpha: x[3] + (y[3] - x[3]) * t)
}

// MARK: - time and easing

func clamp(_ x: CGFloat, _ a: CGFloat = 0, _ b: CGFloat = 1) -> CGFloat { min(b, max(a, x)) }
func prog(_ t: Double, _ start: Double, _ dur: Double) -> CGFloat { clamp(CGFloat((t - start) / max(dur, 1e-6))) }
func lerp(_ a: CGFloat, _ b: CGFloat, _ t: CGFloat) -> CGFloat { a + (b - a) * t }
func outCubic(_ t: CGFloat) -> CGFloat { 1 - pow(1 - t, 3) }
func outQuint(_ t: CGFloat) -> CGFloat { 1 - pow(1 - t, 5) }
func outExpo(_ t: CGFloat) -> CGFloat { t >= 1 ? 1 : 1 - pow(2, -10 * t) }
func inCubic(_ t: CGFloat) -> CGFloat { t * t * t }
func inOutCubic(_ t: CGFloat) -> CGFloat { t < 0.5 ? 4 * t * t * t : 1 - pow(-2 * t + 2, 3) / 2 }
func inOutQuint(_ t: CGFloat) -> CGFloat { t < 0.5 ? 16 * pow(t, 5) : 1 - pow(-2 * t + 2, 5) / 2 }
/// A critically damped settle with a whisper of overshoot (about 1.5 %): things arrive and rest, never bounce.
func settle(_ t: CGFloat) -> CGFloat {
	if t <= 0 { return 0 }
	if t >= 1 { return 1 }
	let w: CGFloat = 9.0
	return 1 - (1 + w * t) * exp(-w * t) + 0.015 * sin(.pi * t) * (1 - t) * 4
}
func lerpRect(_ a: CGRect, _ b: CGRect, _ t: CGFloat) -> CGRect {
	CGRect(x: lerp(a.minX, b.minX, t), y: lerp(a.minY, b.minY, t), width: lerp(a.width, b.width, t),
		height: lerp(a.height, b.height, t))
}

// MARK: - JSON helpers

typealias Obj = [String: Any]
func d(_ o: Obj, _ k: String, _ def: Double = 0) -> Double { (o[k] as? Double) ?? (o[k] as? Int).map(Double.init) ?? def }
func s(_ o: Obj, _ k: String, _ def: String = "") -> String { (o[k] as? String) ?? def }
func arr(_ o: Obj, _ k: String) -> [Obj] { (o[k] as? [Obj]) ?? [] }
func pick(_ o: Obj, _ k: String) -> Obj { (o[k] as? Obj) ?? [:] }

// MARK: - the canvas

let cs = CGColorSpace(name: CGColorSpace.sRGB)!
let ctx = CGContext(data: nil, width: W, height: H, bitsPerComponent: 8, bytesPerRow: W * 4, space: cs,
	bitmapInfo: CGBitmapInfo.byteOrder32Little.rawValue | CGImageAlphaInfo.premultipliedFirst.rawValue)!
ctx.translateBy(x: 0, y: CH)
ctx.scaleBy(x: 1, y: -1)  // y grows downwards from the top-left, like the layout
ctx.setShouldAntialias(true)
ctx.setAllowsFontSmoothing(false)
ctx.interpolationQuality = .high

/// Opacity multiplies down nested drawing (a card at 50 % holding text at 50 % draws the text at 25 %).
var alphaNow: CGFloat = 1
func save(_ f: () -> Void) { let a = alphaNow; ctx.saveGState(); f(); ctx.restoreGState(); alphaNow = a }
func setAlpha(_ a: CGFloat) { alphaNow *= a; ctx.setAlpha(alphaNow) }
func fill(_ r: CGRect, _ c: CGColor, radius: CGFloat = 0) {
	ctx.setFillColor(c)
	if radius > 0 { ctx.addPath(CGPath(roundedRect: r, cornerWidth: radius, cornerHeight: radius, transform: nil)); ctx.fillPath() }
	else { ctx.fill(r) }
}
func stroke(_ r: CGRect, _ c: CGColor, radius: CGFloat = 0, width: CGFloat = 1.5) {
	ctx.setStrokeColor(c)
	ctx.setLineWidth(width)
	ctx.addPath(CGPath(roundedRect: r.insetBy(dx: width / 2, dy: width / 2), cornerWidth: radius, cornerHeight: radius, transform: nil))
	ctx.strokePath()
}
func image(_ img: CGImage, _ r: CGRect, radius: CGFloat = 0, alpha: CGFloat = 1) {
	save {
		if radius > 0 { ctx.addPath(CGPath(roundedRect: r, cornerWidth: radius, cornerHeight: radius, transform: nil)); ctx.clip() }
		setAlpha(alpha)
		ctx.translateBy(x: r.minX, y: r.maxY)
		ctx.scaleBy(x: 1, y: -1)
		ctx.draw(img, in: CGRect(x: 0, y: 0, width: r.width, height: r.height))
	}
}
/// A soft drop shadow under a card, drawn as its own layer so the card's content stays sharp.
func shadow(_ r: CGRect, radius: CGFloat, alpha: CGFloat = 0.45, blur: CGFloat = 40, dy: CGFloat = 18) {
	save {
		ctx.setShadow(offset: CGSize(width: 0, height: -dy), blur: blur, color: CGColor(gray: 0, alpha: alpha))
		fill(r, C("bg"), radius: radius)
	}
}

// MARK: - type

enum Face { case sans, mono }
var fontCache: [String: CTFont] = [:]
func font(_ size: CGFloat, _ weight: NSFont.Weight = .regular, _ face: Face = .sans, italic: Bool = false) -> CTFont {
	let key = "\(size)-\(weight.rawValue)-\(face)-\(italic)"
	if let f = fontCache[key] { return f }
	var f: CTFont = face == .mono ? NSFont.monospacedSystemFont(ofSize: size, weight: weight) as CTFont
		: NSFont.systemFont(ofSize: size, weight: weight) as CTFont
	if italic, let it = CTFontCreateCopyWithSymbolicTraits(f, size, nil, .traitItalic, .traitItalic) { f = it }
	fontCache[key] = f
	return f
}
func ctline(_ str: String, _ f: CTFont, _ color: CGColor, kern: CGFloat = 0) -> CTLine {
	let attrs: [NSAttributedString.Key: Any] = [
		NSAttributedString.Key(kCTFontAttributeName as String): f,
		NSAttributedString.Key(kCTForegroundColorAttributeName as String): color,
		NSAttributedString.Key(kCTKernAttributeName as String): kern,
	]
	return CTLineCreateWithAttributedString(NSAttributedString(string: str, attributes: attrs))
}
func width(_ str: String, _ f: CTFont, kern: CGFloat = 0) -> CGFloat {
	CGFloat(CTLineGetTypographicBounds(ctline(str, f, C("text"), kern: kern), nil, nil, nil))
}
@discardableResult
func text(_ str: String, _ x: CGFloat, _ baseline: CGFloat, _ f: CTFont, _ color: CGColor, align: CGFloat = 0,
	kern: CGFloat = 0, alpha: CGFloat = 1) -> CGFloat {
	let l = ctline(str, f, color, kern: kern)
	let w = CGFloat(CTLineGetTypographicBounds(l, nil, nil, nil))
	save {
		setAlpha(alpha)
		ctx.textMatrix = CGAffineTransform(scaleX: 1, y: -1)
		ctx.textPosition = CGPoint(x: x - w * align, y: baseline)
		CTLineDraw(l, ctx)
	}
	return w
}
/// Words of a line: `*word` is the accent word (one accent colour in the whole piece).
struct Word { let text: String; let accent: Bool }
func words(_ line: String) -> [Word] {
	line.split(separator: " ", omittingEmptySubsequences: true).map {
		$0.hasPrefix("*") ? Word(text: String($0.dropFirst()), accent: true) : Word(text: String($0), accent: false)
	}
}

/// Kinetic type: each word rises into place behind a mask at its baseline (an editorial reveal, ease-out quint),
/// staggered; on exit the line lifts away and fades. Returns the line's width.
@discardableResult
func kinetic(_ line: String, x: CGFloat, baseline: CGFloat, size: CGFloat, weight: NSFont.Weight, color: CGColor,
	t: Double, at: Double, exit: Double = 1e9, stagger: Double = 0.06, align: CGFloat = 0.5, dur: Double = 0.7,
	face: Face = .sans, kern: CGFloat = -0.5) -> CGFloat {
	let f = font(size, weight, face)
	let ws = words(line)
	let space = width(" ", f)
	let widths = ws.map { width($0.text, f, kern: kern) }
	let total = widths.reduce(0, +) + space * CGFloat(max(ws.count - 1, 0))
	var cx = x - total * align
	let asc = CTFontGetAscent(f), desc = CTFontGetDescent(f)
	let out = outCubic(prog(t, exit, 0.45))
	if out >= 1 { return total }
	for (i, w) in ws.enumerated() {
		let p = outQuint(prog(t, at + Double(i) * stagger, dur))
		if p > 0 {
			save {
				let band = CGRect(x: cx - 4, y: baseline - asc - 8 - out * size * 0.4, width: widths[i] + 8 + space,
					height: asc + desc + 16)
				ctx.clip(to: band)
				let dy = (1 - p) * (asc + desc) * 0.9 - out * size * 0.4
				text(w.text, cx, baseline + dy, f, w.accent ? C("accent") : color, kern: kern,
					alpha: clamp(p * 1.6) * (1 - out))
			}
		}
		cx += widths[i] + space
	}
	return total
}

// MARK: - footage (ffmpeg pipes, read in order)

final class Reader {
	let file: String, start: Double, w: Int, h: Int, step: Int
	var proc: Process?
	var out: FileHandle?
	var cur = -1
	var img: CGImage?
	init(file: String, start: Double, w: Int, h: Int, step: Int) {
		self.file = file; self.start = start; self.w = w; self.h = h; self.step = step
	}
	func open(_ k: Int) {
		close()
		let p = Process()
		p.executableURL = URL(fileURLWithPath: FFMPEG)
		let at = start + Double(k * step) / FPS
		var vf = "scale=\(w):\(h):flags=lanczos:in_color_matrix=bt709:in_range=tv,format=bgra"
		if step > 1 { vf = "select='not(mod(n\\,\(step)))'," + vf }
		p.arguments = ["-v", "fatal", "-ss", String(format: "%.4f", at), "-i", file, "-an", "-vf", vf,
			"-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "bgra", "-"]
		let pipe = Pipe()
		p.standardOutput = pipe
		p.standardError = FileHandle.standardError
		try! p.run()
		proc = p
		out = pipe.fileHandleForReading
		cur = k - 1
	}
	func close() {
		if let p = proc, p.isRunning { p.terminate() }
		proc = nil; out = nil
	}
	func read() -> Data? {
		guard let fh = out else { return nil }
		let n = w * h * 4
		var data = Data(capacity: n)
		while data.count < n {
			let part = fh.readData(ofLength: n - data.count)
			if part.isEmpty { return nil }
			data.append(part)
		}
		return data
	}
	func frame(_ k: Int) -> CGImage? {
		if proc == nil || k < cur || k > cur + 90 { open(max(k, 0)) }
		while cur < k {
			guard let data = read() else { cur = k; return img }
			cur += 1
			if cur == k {
				img = CGImage(width: w, height: h, bitsPerComponent: 8, bitsPerPixel: 32, bytesPerRow: w * 4, space: cs,
					bitmapInfo: CGBitmapInfo(rawValue: CGBitmapInfo.byteOrder32Little.rawValue | CGImageAlphaInfo.noneSkipFirst.rawValue),
					provider: CGDataProvider(data: data as CFData)!, decode: nil, shouldInterpolate: true, intent: .defaultIntent)
			}
		}
		return img
	}
}
let media = J["media"] as! [String: Obj]
var readers: [String: Reader] = [:]
/// The frame of `key`'s video at `inSec` + (t - since), at `step` source frames per output frame.
func footage(_ key: String, inSec: Double, since: Double, t: Double, step: Int = 1) -> CGImage? {
	guard let m = media[key] else { return nil }
	let id = "\(key)@\(inSec)x\(step)"
	let r = readers[id] ?? {
		let r = Reader(file: s(m, "file"), start: inSec, w: Int(d(m, "w")), h: Int(d(m, "h")), step: step)
		readers[id] = r
		return r
	}()
	return r.frame(max(0, Int(((t - since) * FPS).rounded())))
}
func aspect(_ key: String) -> CGFloat { let m = media[key] ?? [:]; return CGFloat(d(m, "w", 16) / d(m, "h", 9)) }

// MARK: - pieces

func background() {
	fill(CGRect(x: 0, y: 0, width: CW, height: CH), C("bg"))
	save {
		let g = CGGradient(colorsSpace: cs, colors: [C("bg2"), C("bg2", 0)] as CFArray, locations: [0, 1])!
		ctx.drawRadialGradient(g, startCenter: CGPoint(x: CW / 2, y: CH * 0.32), startRadius: 0,
			endCenter: CGPoint(x: CW / 2, y: CH * 0.32), endRadius: max(CW, CH) * 0.75, options: [])
	}
}
/// A label chip: monospace code on a dark glass pill (the only chrome over footage).
func chip(_ str: String, x: CGFloat, y: CGFloat, size: CGFloat, alpha: CGFloat, align: CGFloat = 0, accentFirst: Bool = false) {
	if alpha <= 0 { return }
	let f = font(size, .medium, .mono)
	let w = width(str, f)
	let padX = size * 0.75, h = size * 1.9
	let r = CGRect(x: x - (w + 2 * padX) * align, y: y, width: w + 2 * padX, height: h)
	save {
		setAlpha(alpha)
		fill(r, CGColor(srgbRed: 0.07, green: 0.067, blue: 0.06, alpha: 0.78), radius: h / 2)
		stroke(r, C("text", 0.14), radius: h / 2, width: 1.2)
		let base = r.minY + h / 2 + size * 0.36
		if accentFirst, let sp = str.firstIndex(of: " ") {
			let head = String(str[..<sp])
			let hw = text(head, r.minX + padX, base, f, C("accent"))
			text(String(str[sp...]), r.minX + padX + hw, base, f, C("text"))
		} else {
			text(str, r.minX + padX, base, f, C("text"))
		}
	}
}
/// The logo: assets/icon.svg's pixel quads (make.py reads them), drawn at `size` with its top-left at `o`.
let quads = (J["logo"] as? [Obj]) ?? []
func logo(_ o: CGPoint, _ size: CGFloat, t: Double = 1e9, at: Double = -1e9, assemble: Bool = false, alpha: CGFloat = 1,
	from: CGPoint? = nil) {
	let k = size / 64
	save {
		setAlpha(alpha)
		for (i, q) in quads.enumerated() {
			let pts = (q["p"] as! [[Double]]).map { CGPoint(x: o.x + CGFloat($0[0]) * k, y: o.y + CGFloat($0[1]) * k) }
			var p: CGFloat = 1
			var off = CGPoint.zero
			if assemble {
				let order = d(q, "o")  // 0..1, from make.py: top face first, then the sides, by distance
				p = outQuint(prog(t, at + order * 0.9, 0.75))
				if p <= 0 { continue }
				let seed = Double(i) * 12.9898
				let ang = CGFloat(sin(seed) * 43758.5453).truncatingRemainder(dividingBy: 1) * .pi * 2
				if let src = from {
					let c = CGPoint(x: pts.map { $0.x }.reduce(0, +) / 4, y: pts.map { $0.y }.reduce(0, +) / 4)
					let start = CGPoint(x: src.x + cos(ang) * 40, y: src.y + sin(ang) * 40)
					// An arc, not a straight line: the pixels swing up out of the chart and settle into the block.
					let lift = sin(.pi * p) * -120
					off = CGPoint(x: (start.x - c.x) * (1 - p), y: (start.y - c.y) * (1 - p) + lift * (1 - p))
				} else {
					off = CGPoint(x: cos(ang) * 46 * k * (1 - p), y: (sin(ang) * 46 - 30) * k * (1 - p))
				}
			}
			ctx.setFillColor(hex(s(q, "c"), clamp(p * 1.4)))
			ctx.move(to: CGPoint(x: pts[0].x + off.x, y: pts[0].y + off.y))
			for pt in pts.dropFirst() { ctx.addLine(to: CGPoint(x: pt.x + off.x, y: pt.y + off.y)) }
			ctx.closePath()
			ctx.fillPath()
		}
	}
}
func check(_ c: CGPoint, _ r: CGFloat, _ p: CGFloat, color: CGColor) {
	if p <= 0 { return }
	save {
		ctx.setStrokeColor(color)
		ctx.setLineWidth(r * 0.16)
		ctx.setLineCap(.round)
		ctx.setLineJoin(.round)
		let a = CGPoint(x: c.x - r * 0.42, y: c.y + r * 0.02), b = CGPoint(x: c.x - r * 0.1, y: c.y + r * 0.32),
			e = CGPoint(x: c.x + r * 0.46, y: c.y - r * 0.32)
		let l1 = hypot(b.x - a.x, b.y - a.y), l2 = hypot(e.x - b.x, e.y - b.y)
		let len = (l1 + l2) * p
		ctx.move(to: a)
		if len <= l1 { ctx.addLine(to: CGPoint(x: a.x + (b.x - a.x) * len / l1, y: a.y + (b.y - a.y) * len / l1)) }
		else {
			ctx.addLine(to: b)
			let q = (len - l1) / l2
			ctx.addLine(to: CGPoint(x: b.x + (e.x - b.x) * q, y: b.y + (e.y - b.y) * q))
		}
		ctx.strokePath()
	}
}

// MARK: - the terminal

/// Output styling: the first word of a CLI line (RESULT, VIDEO, STAGE …) muted, verdict words in the accent.
func termLine(_ str: String, _ x: CGFloat, _ base: CGFloat, _ f: CTFont, alpha: CGFloat) {
	if str.hasPrefix("$ ") {
		let w = text("$ ", x, base, f, C("accent"), alpha: alpha)
		text(String(str.dropFirst(2)), x + w, base, f, C("text"), alpha: alpha)
		return
	}
	if str.hasPrefix("  ") { text(str, x, base, f, C("muted"), alpha: alpha); return }
	var cx = x
	let parts = str.split(separator: " ", omittingEmptySubsequences: false).map(String.init)
	let sp = width(" ", f)
	for (i, p) in parts.enumerated() {
		var c = C("text")
		if i == 0 && p == p.uppercased() && p.count >= 3 && p.first!.isLetter { c = C("muted") }
		if ["PASS", "ok", "locked", "READY", "identical"].contains(p) { c = C("accent") }
		if p == "FAIL" { c = C("warn") }
		if !p.isEmpty { cx += text(p, cx, base, f, c, alpha: alpha) }
		if i < parts.count - 1 { cx += sp }
	}
}
/// Wraps a line at `cols` characters on word boundaries (a `\n` is a hard break), continuation rows indented.
func wrap(_ str: String, _ cols: Int) -> [String] {
	var out: [String] = []
	for (pi, para) in str.components(separatedBy: "\n").enumerated() {
		var line = pi == 0 ? "" : ""
		for w in para.split(separator: " ", omittingEmptySubsequences: false) {
			let cand = line.isEmpty ? String(w) : line + " " + w
			if cand.count > cols && !line.isEmpty { out.append(line); line = "    " + w } else { line = cand }
		}
		out.append(line)
	}
	return out
}
struct TermLine { let text: String; let at: Double; let typed: Bool; let cps: Double }
/// A terminal window: `lines` appear at their times (a typed one character by character), newest at the bottom.
func terminal(_ r: CGRect, lines: [TermLine], t: Double, size: CGFloat, chrome: CGFloat, title: String, alpha: CGFloat = 1,
	centre: CGFloat = 0) {
	if alpha <= 0 { return }
	let radius: CGFloat = 18
	save {
		setAlpha(alpha)
		if chrome > 0 {
			save {
				setAlpha(alpha * chrome)
				shadow(r, radius: radius, alpha: 0.5)
				fill(r, C("panel"), radius: radius)
				stroke(r, C("line"), radius: radius)
				let bar: CGFloat = 50
				save {
					ctx.addPath(CGPath(roundedRect: r, cornerWidth: radius, cornerHeight: radius, transform: nil))
					ctx.clip()
					fill(CGRect(x: r.minX, y: r.minY, width: r.width, height: bar), C("panel2"))
					fill(CGRect(x: r.minX, y: r.minY + bar, width: r.width, height: 1.2), C("line"))
				}
				for i in 0..<3 {
					ctx.setFillColor(C("dim"))
					ctx.fillEllipse(in: CGRect(x: r.minX + 22 + CGFloat(i) * 22, y: r.minY + bar / 2 - 6, width: 12, height: 12))
				}
				text(title, r.midX, r.minY + bar / 2 + 6, font(16, .medium, .mono), C("muted"), align: 0.5)
			}
		}
		let f = font(size, .regular, .mono)
		let cw = width("M", f)
		let lh = size * 1.5
		let pad: CGFloat = 30
		// Before the window appears, the one typed row sits at the middle of the frame (`centre` 1 → 0 as it opens).
		let top = r.minY + 50 + pad * 0.8 + centre * (CH / 2 - (r.minY + 50 + pad * 0.8 + size * 1.05 - size * 0.4))
		let content = CGRect(x: r.minX + pad, y: top, width: r.width - 2 * pad, height: r.maxY - pad * 0.6 - top)
		let cols = max(10, Int(content.width / cw))
		// Visible rows: every line that has started, typed ones cut to what is typed so far.
		var rows: [(String, CGFloat, Bool)] = []  // text, alpha, is the typing row
		var typing = false
		for l in lines where t >= l.at {
			var str = l.text
			var a: CGFloat = 1
			if l.typed {
				let n = Int(((t - l.at) * l.cps).rounded(.down))
				if n < str.count { str = String(str.prefix(n)); typing = true }
			} else { a = outCubic(prog(t, l.at, 0.22)) }
			let pieces = wrap(str, cols)
			for (i, p) in pieces.enumerated() {
				// Continuation rows of a "$ " line are not prompts.
				let shown = (i > 0 && p.hasPrefix("$ ")) ? " " + p : p
				rows.append((shown, a, l.typed && i == pieces.count - 1))
			}
		}
		if rows.isEmpty { rows.append(("$ ", 1, true)) }
		let fit = max(1, Int(content.height / lh))
		let firstRow = max(0, rows.count - fit)
		save {
			if centre < 0.01 { ctx.clip(to: content.insetBy(dx: -4, dy: -4)) }
			for (i, row) in rows[firstRow...].enumerated() {
				let base = content.minY + CGFloat(i) * lh + size * 1.05
				let dx = (1 - row.1) * 14
				termLine(row.0, content.minX + dx, base, f, alpha: row.1)
				// The cursor: on the last row, solid while typing, blinking when idle.
				if i == rows.count - 1 - firstRow {
					let on = typing || (Int(t * 2) % 2 == 0)
					let last = row.0
					var cx = content.minX
					if last.hasPrefix("$ ") { cx += width("$ ", f) + width(String(last.dropFirst(2)), f) }
					else if row.2 { cx += width(last, f) }
					else { continue }
					if on { fill(CGRect(x: cx + 2, y: base - size * 0.82, width: cw * 0.9, height: size * 1.05), C("accent", 0.9)) }
				}
			}
		}
	}
}
func termLines(_ o: Obj) -> [TermLine] {
	arr(o, "lines").map { TermLine(text: s($0, "text"), at: d($0, "t"), typed: ($0["typed"] as? Bool) ?? false, cps: d($0, "cps", 24)) }
}

// MARK: - scenes

/// The kicker over a canvas section: one size everywhere (56 px landscape, 64 px vertical), left on the grid.
let KICK: CGFloat = V ? 64 : 56
let MARGIN: CGFloat = V ? 60 : 120
func kicker(_ str: String, _ t: Double, at: Double, exit: Double, top: CGFloat? = nil) {
	let lines = str.components(separatedBy: "\n")
	let y0 = top ?? (V ? 210 : 176)
	for (i, l) in lines.enumerated() {
		kinetic(l, x: MARGIN, baseline: y0 + CGFloat(i) * KICK * 1.12, size: KICK, weight: .medium, color: C("text"), t: t,
			at: at + Double(i) * 0.12, exit: exit, align: 0, kern: -1)
	}
}

func sceneMake(_ o: Obj, _ t: Double) {
	let dock = d(o, "dock"), exitAt = d(o, "exit")
	let enter = d(o, "enter")
	let pd = inOutQuint(prog(t, dock, 0.9))
	let out = inCubic(prog(t, exitAt, 0.45))
	let big = V ? CGRect(x: 60, y: 640, width: 960, height: 600) : CGRect(x: 300, y: 250, width: 1320, height: 580)
	let docked = V ? CGRect(x: 60, y: 150, width: 960, height: 560) : CGRect(x: 120, y: 96, width: 1680, height: 330)
	var r = lerpRect(big, docked, pd)
	r.origin.y -= out * 50
	let chrome = outCubic(prog(t, enter - 0.15, 0.5))
	let open = inOutCubic(prog(t, enter, 0.7))
	// The vertical terminal keeps one size and width the whole time, so nothing reflows while it moves.
	let size = V ? 25 : lerp(lerp(27, 26, open), 24, pd)
	terminal(r, lines: termLines(o), t: t, size: size, chrome: chrome, title: s(o, "title"), alpha: 1 - out, centre: 1 - open)

	// The pipeline: every step at once, lighting in order with the file it writes (no scrolling).
	let nodes = arr(o, "nodes")
	if nodes.isEmpty || t < dock + 0.3 { return }
	let appear = outCubic(prog(t, dock + 0.45, 0.7))
	let times = nodes.map { d($0, "t") }
	save {
		setAlpha(appear * (1 - out))
		kicker(s(o, V ? "header_v" : "header"), t, at: dock + 0.5, exit: exitAt, top: V ? 800 : 520)
		var rects: [CGRect] = []
		for i in 0..<nodes.count {
			if V {
				rects.append(CGRect(x: 60, y: 900 + CGFloat(i) * 88, width: 960, height: 74))
			} else {
				let row = i < 6 ? 0 : 1, col = i < 6 ? i : i - 6
				rects.append(CGRect(x: 120 + CGFloat(col) * 284, y: 580 + CGFloat(row) * 176, width: 260, height: 136))
			}
		}
		// Connectors first, under the cards, filling with the light as it travels to the next card.
		for i in 0..<(nodes.count - 1) {
			let a = rects[i], b = rects[i + 1]
			let fillP = clamp(CGFloat((t - times[i]) / max(times[i + 1] - times[i], 0.01)))
			var pts: [CGPoint]
			if V { pts = [CGPoint(x: a.minX + 40, y: a.maxY), CGPoint(x: b.minX + 40, y: b.minY)] }
			else if i == 5 {
				let midY = (a.maxY + b.minY) / 2
				pts = [CGPoint(x: a.midX, y: a.maxY), CGPoint(x: a.midX, y: midY), CGPoint(x: b.midX, y: midY), CGPoint(x: b.midX, y: b.minY)]
			} else { pts = [CGPoint(x: a.maxX, y: a.midY), CGPoint(x: b.minX, y: b.midY)] }
			polyline(pts, 1, C("line"), 2)
			if fillP > 0 { polyline(pts, fillP, C("accent"), 2) }
		}
		for (i, n) in nodes.enumerated() {
			var rect = rects[i]
			let rise = (1 - outCubic(prog(t, dock + 0.5 + Double(i) * 0.03, 0.7))) * 30
			rect.origin.y += rise
			let lit = outCubic(prog(t, times[i], 0.3))
			let pop = settle(prog(t, times[i], 0.5))
			if lit > 0 { rect.origin.y -= (1 - pop) * 6 }
			fill(rect, mix(C("panel"), C("panel2"), lit), radius: 14)
			stroke(rect, mix(C("line"), C("accent", 0.85), lit), radius: 14, width: 1.5)
			let num = String(format: "%02d", i + 1)
			if V {
				text(num, rect.minX + 24, rect.midY + 8, font(22, .medium, .mono), mix(C("dim"), C("accent"), lit))
				text(s(n, "name"), rect.minX + 84, rect.midY + 11, font(32, .semibold), mix(C("muted"), C("text"), lit))
				text(s(n, "file"), rect.maxX - 70, rect.midY + 9, font(24, .regular, .mono), mix(C("dim"), C("muted"), lit), align: 1)
			} else {
				text(num, rect.minX + 22, rect.minY + 38, font(20, .medium, .mono), mix(C("dim"), C("accent"), lit))
				text(s(n, "name"), rect.minX + 22, rect.minY + 86, font(31, .semibold), mix(C("muted"), C("text"), lit))
				text(s(n, "file"), rect.minX + 22, rect.minY + 118, font(21, .regular, .mono), mix(C("dim"), C("muted"), lit))
			}
			let dot = V ? CGPoint(x: rect.maxX - 34, y: rect.midY) : CGPoint(x: rect.maxX - 28, y: rect.minY + 31)
			ctx.setStrokeColor(mix(C("dim"), C("accent"), lit))
			ctx.setLineWidth(2)
			ctx.strokeEllipse(in: CGRect(x: dot.x - 7, y: dot.y - 7, width: 14, height: 14))
			if lit > 0 {
				ctx.setFillColor(C("accent", lit))
				ctx.fillEllipse(in: CGRect(x: dot.x - 7, y: dot.y - 7, width: 14, height: 14))
				let ring = prog(t, times[i], 0.6)
				if ring < 1 {
					let rr = 7 + outCubic(ring) * 22
					ctx.setStrokeColor(C("accent", (1 - ring) * 0.6))
					ctx.setLineWidth(2)
					ctx.strokeEllipse(in: CGRect(x: dot.x - rr, y: dot.y - rr, width: 2 * rr, height: 2 * rr))
				}
			}
		}
		let foot = s(o, "footer")
		if !foot.isEmpty && !V {
			text(foot, 120, 970, font(21, .regular, .mono), C("muted"), alpha: outCubic(prog(t, dock + 1.0, 0.6)))
		}
	}
}

/// A polyline drawn up to `p` (0-1) of its length.
func polyline(_ pts: [CGPoint], _ p: CGFloat, _ color: CGColor, _ w: CGFloat) {
	var lens: [CGFloat] = []
	for i in 1..<pts.count { lens.append(hypot(pts[i].x - pts[i - 1].x, pts[i].y - pts[i - 1].y)) }
	var left = lens.reduce(0, +) * p
	ctx.setStrokeColor(color)
	ctx.setLineWidth(w)
	ctx.setLineCap(.round)
	ctx.setLineJoin(.round)
	ctx.move(to: pts[0])
	for i in 1..<pts.count {
		if left <= 0 { break }
		let f = min(1, left / max(lens[i - 1], 0.01))
		ctx.addLine(to: CGPoint(x: pts[i - 1].x + (pts[i].x - pts[i - 1].x) * f, y: pts[i - 1].y + (pts[i].y - pts[i - 1].y) * f))
		left -= lens[i - 1]
	}
	ctx.strokePath()
}

func sceneTitle(_ o: Obj, _ t: Double) {
	let exitAt = d(o, "exit", 1e9)
	for l in arr(o, V ? "lines_v" : "lines") {
		let y = CGFloat(d(l, "y")) * CH
		let x = CGFloat(d(l, "x", 0.5)) * CW
		let w: NSFont.Weight = s(l, "weight") == "regular" ? .regular : (s(l, "weight") == "bold" ? .bold : (s(l, "weight") == "medium" ? .medium : .semibold))
		kinetic(s(l, "text"), x: x, baseline: y, size: CGFloat(d(l, "size", 72)), weight: w,
			color: C(s(l, "color", "text")), t: t, at: d(l, "t"), exit: exitAt, stagger: d(l, "stagger", 0.07),
			align: CGFloat(d(l, "align", 0.5)), face: s(l, "face") == "mono" ? .mono : .sans, kern: s(l, "face") == "mono" ? 0 : -1)
	}
}

/// The chip over footage: a dark glass plate that stays across cuts (its width eases to the new text), the script
/// line that made the clip in monospace, and under it what that is in plain words and where it came from.
func footChip(_ clips: [Obj], _ idx: Int, _ t: Double, x: CGFloat, y: CGFloat, alpha: CGFloat) {
	if alpha <= 0 { return }
	let code = font(V ? 27 : 26, .medium, .mono), tagF = font(V ? 24 : 22, .regular)
	func lab(_ c: Obj) -> String { V ? s(c, "label_v", s(c, "label")) : s(c, "label") }
	func tg(_ c: Obj) -> String { V ? s(c, "tag_v", s(c, "tag")) : s(c, "tag") }
	func w(_ c: Obj) -> CGFloat { max(width(lab(c), code), width(tg(c), tagF)) + 48 }
	let cur = clips[idx]
	let since = t - d(cur, "at")
	let grow = idx > 0 ? inOutCubic(prog(t, d(cur, "at"), 0.3)) : 1
	let pw = idx > 0 ? lerp(w(clips[idx - 1]), w(cur), grow) : w(cur)
	let h: CGFloat = V ? 108 : 100
	let r = CGRect(x: x, y: y, width: pw, height: h)
	save {
		setAlpha(alpha)
		fill(r, CGColor(srgbRed: 0.05, green: 0.047, blue: 0.043, alpha: 0.82), radius: 16)
		stroke(r, C("text", 0.12), radius: 16, width: 1.2)
		save {
			ctx.clip(to: r.insetBy(dx: 2, dy: 2))
			// The text changes on the cut frame itself: the new text is there at once, sliding up a few pixels.
			let a = outCubic(clamp(CGFloat(since / 0.14)))
			let dy = (1 - a) * 10
			let label = lab(cur)
			if let sp = label.firstIndex(of: "=") {
				let k = String(label[..<sp])
				let kw = text(k, r.minX + 24, r.minY + 42 + dy, code, C("accent"), alpha: a)
				text(String(label[sp...]), r.minX + 24 + kw, r.minY + 42 + dy, code, C("text"), alpha: a)
			} else {
				text(label, r.minX + 24, r.minY + 42 + dy, code, C("text"), alpha: a)
			}
			text(tg(cur), r.minX + 24, r.minY + 80 + dy, tagF, C("muted"), alpha: a)
		}
	}
}
func sceneFootage(_ o: Obj, _ t: Double) {
	let clips = arr(o, "clips")
	guard let idx = clips.lastIndex(where: { t >= d($0, "at") }) else { return }
	let c = clips[idx]
	let at = d(c, "at"), dur = d(c, "dur")
	// The vertical cut plays the tool's own 9:16 re-frame of each clip, full bleed.
	let key = V ? s(c, "media_v", s(c, "media")) : s(c, "media")
	let inSec = V ? d(c, "in_v", d(c, "in")) : d(c, "in")
	guard let img = footage(key, inSec: inSec, since: at, t: t) else { return }
	let z0 = CGFloat(d(c, "z0", 1.0)), z1 = CGFloat(d(c, "z1", 1.035))
	let z = lerp(z0, z1, CGFloat((t - at) / dur))
	let full = CGRect(x: 0, y: 0, width: CW, height: CH)
	let intro = d(c, "intro", 0)
	let p = intro > 0 ? inOutQuint(prog(t, at, intro)) : 1
	var card = V ? CGRect(x: 216, y: 576, width: 648, height: 1152) : CGRect(x: 384, y: 216, width: 1152, height: 648)
	// Out of the terminal: the film starts as a small frame where the VIDEO line was printed.
	if s(c, "intro_from") == "terminal" {
		card = V ? CGRect(x: 440, y: 250, width: 200, height: 356) : CGRect(x: 1200, y: 150, width: 480, height: 270)
	}
	let r = lerpRect(card, full, p)
	let radius = lerp(22, 0, p)
	save {
		if p < 1 { shadow(r, radius: radius, alpha: 0.5 * (1 - p)) }
		ctx.addPath(CGPath(roundedRect: r, cornerWidth: radius, cornerHeight: radius, transform: nil))
		ctx.clip()
		image(img, r.insetBy(dx: -r.width * (z - 1) / 2, dy: -r.height * (z - 1) / 2))
	}
	let first = d(clips[0], "at") + intro
	let ca = outCubic(prog(t, first - 0.1, 0.3)) * (1 - outCubic(prog(t, d(o, "to") - 0.25, 0.25)))
	if V {
		// Title over the blurred top of the re-frame, the chip over its blurred bottom (above the apps' buttons).
		let title = s(o, "title_v")
		if !title.isEmpty {
			save {
				let g = CGGradient(colorsSpace: cs, colors: [C("bg", 0.55), C("bg", 0)] as CFArray, locations: [0, 1])!
				setAlpha(ca)
				ctx.drawLinearGradient(g, start: CGPoint(x: 0, y: 0), end: CGPoint(x: 0, y: 520), options: [])
			}
			kicker(title, t, at: first - 0.1, exit: d(o, "to") - 0.3, top: 250)
		}
		footChip(clips, idx, t, x: 60, y: 1330, alpha: ca)
	} else {
		footChip(clips, idx, t, x: 56, y: 52, alpha: ca)
	}
}

func sceneSplit(_ o: Obj, _ t: Double) {
	let from = d(o, "from"), to = d(o, "to")
	let a = pick(o, "a"), b = pick(o, "b")
	let p = inOutQuint(prog(t, from, 0.9))
	let out = inCubic(prog(t, to - 0.45, 0.45))
	let full = CGRect(x: 0, y: 0, width: CW, height: CH)
	let ra = V ? CGRect(x: 60, y: 330, width: 960, height: 540) : CGRect(x: 120, y: 250, width: 1040, height: 585)
	let rb = V ? CGRect(x: 290, y: 940, width: 500, height: 889) : CGRect(x: 1290, y: 120, width: 486, height: 864)
	var rA = V ? lerpRect(CGRect(x: 0, y: (CH - 608) / 2, width: CW, height: 608), ra, p) : lerpRect(full, ra, p)
	rA.origin.y -= out * 40
	if let img = footage(s(a, "media"), inSec: d(a, "in"), since: from, t: t) {
		save {
			setAlpha(1 - out)
			if p > 0.02 { shadow(rA, radius: 18 * p) }
			let radius = 18 * p
			ctx.addPath(CGPath(roundedRect: rA, cornerWidth: radius, cornerHeight: radius, transform: nil))
			ctx.clip()
			image(img, rA)
		}
	}
	let pb = outQuint(prog(t, from + 0.4, 0.9))
	var rB = rb
	if V { rB.origin.y += (1 - pb) * 160 } else { rB.origin.x += (1 - pb) * 160 }
	rB.origin.y -= out * 40
	if pb > 0, let img = footage(s(b, "media"), inSec: d(b, "in"), since: from, t: t) {
		save {
			setAlpha(clamp(pb * 1.5) * (1 - out))
			shadow(rB, radius: 26)
			save {
				ctx.addPath(CGPath(roundedRect: rB, cornerWidth: 26, cornerHeight: 26, transform: nil))
				ctx.clip()
				image(img, rB)
			}
			stroke(rB, C("text", 0.18), radius: 26, width: 2)
		}
	}
	let la = outCubic(prog(t, from + 0.9, 0.5)) * (1 - out)
	let lf = font(V ? 24 : 22, .regular, .mono)
	if V {
		text(s(a, "label"), ra.minX, ra.maxY + 44 - out * 40, lf, C("muted"), alpha: la)
		chip(s(b, "label_v", s(b, "label")), x: CW / 2, y: rb.maxY - 76 - out * 40, size: 20, alpha: la, align: 0.5)
	} else {
		text(s(a, "label"), ra.minX, ra.maxY + 48 - out * 40, lf, C("muted"), alpha: la)
		text(s(b, "label"), rb.minX, rb.maxY + 48 - out * 40, lf, C("muted"), alpha: la)
	}
	kicker(s(o, V ? "header_v" : "header"), t, at: from + 0.5, exit: to - 0.45, top: V ? 200 : 176)
}

/// Where the determinism cards sit (the voice section's card starts from the second one).
func detCards() -> [CGRect] {
	V ? [CGRect(x: 60, y: 330, width: 960, height: 540), CGRect(x: 60, y: 920, width: 960, height: 540)]
		: [CGRect(x: 120, y: 236, width: 800, height: 450), CGRect(x: 1000, y: 236, width: 800, height: 450)]
}
func sceneDeterminism(_ o: Obj, _ t: Double) {
	let to = d(o, "to"), panel = d(o, "panel"), run = d(o, "run"), done = d(o, "done")
	sceneTitle(["lines": o["lines"] ?? [], "lines_v": o["lines_v"] ?? [], "exit": panel - 0.5], t)
	if t < panel - 0.1 { return }
	let out = inCubic(prog(t, to - 0.4, 0.4))
	let enter = outQuint(prog(t, panel, 0.9))
	let hashes = (o["hashes"] as? [[Any]]) ?? []
	let step = Int(d(o, "step", 10))
	let total = Int(d(o, "total"))
	let shownMax = (total - 1) / step
	// Fast-forward, easing out: quick at first, settling onto the last frame and the check.
	let ff = outCubic(prog(t, run, done - run))
	let k = t < run ? 0 : Int((ff * CGFloat(shownMax)).rounded())
	let shownFrame = min(total - 1, k * step)
	let counted = t < run ? 0 : (t >= done ? total : min(total - 1, shownFrame + 1))
	let finished = t >= done
	let cards = detCards()
	let keys = [s(o, "a"), s(o, "b")]
	let names = [s(o, "a_label"), s(o, "b_label")]
	save {
		setAlpha(enter)
		kicker(s(o, V ? "header_v" : "header"), t, at: panel, exit: to - 0.4)
		save {
			setAlpha(1 - out)
			for i in 0..<2 {
				var r = cards[i]
				r.origin.y += (1 - enter) * 50
				// The second card carries into the next section, so only the first one fades on the way out.
				if i == 1 && out > 0 { continue }
				drawDetCard(r, keys[i], names[i], k, step, run, finished, hashes, shownFrame, i)
			}
		}
		if out > 0 {
			// Stays fully drawn while the voice section's card grows out of it.
			drawDetCard(cards[1], keys[1], names[1], k, step, run, finished, hashes, shownFrame, 1)
		}
		save {
			setAlpha(1 - out)
			let mid = V ? CGPoint(x: CW / 2, y: (cards[0].maxY + cards[1].minY) / 2) : CGPoint(x: CW / 2, y: cards[0].midY)
			let rr: CGFloat = V ? 24 : 30
			ctx.setFillColor(t >= run ? C("accent") : C("dim"))
			ctx.fillEllipse(in: CGRect(x: mid.x - rr, y: mid.y - rr, width: 2 * rr, height: 2 * rr))
			text("=", mid.x, mid.y + rr * 0.42, font(rr * 1.3, .bold), C("bg"), align: 0.5)
			let cy: CGFloat = V ? 1640 : 840
			let count = String(format: "%d / %d", counted, total)
			let fc = font(84, .semibold, .mono)
			let cw = text(count, MARGIN, cy, fc, finished ? C("accent") : C("text"))
			text(s(o, "unit"), MARGIN + cw + 28, cy, font(V ? 34 : 32, .medium), C("muted"))
			let bar = CGRect(x: MARGIN, y: cy + 40, width: CW - 2 * MARGIN, height: 8)
			fill(bar, C("line"), radius: 4)
			fill(CGRect(x: bar.minX, y: bar.minY, width: bar.width * CGFloat(counted) / CGFloat(max(total, 1)), height: bar.height),
				C("accent"), radius: 4)
			let cp = outCubic(prog(t, done, 0.4))
			if cp > 0 { check(CGPoint(x: CW - MARGIN - 34, y: cy - 30), 48, cp, color: C("accent")) }
			let note = s(o, V ? "note_v" : "note")
			for (i, l) in note.components(separatedBy: "\n").enumerated() {
				text(l, MARGIN, cy + 100 + CGFloat(i) * 34, font(22, .regular, .mono), C("muted"), alpha: outCubic(prog(t, done, 0.6)))
			}
		}
	}
}
func drawDetCard(_ r: CGRect, _ key: String, _ name: String, _ k: Int, _ step: Int, _ run: Double, _ finished: Bool,
	_ hashes: [[Any]], _ shownFrame: Int, _ i: Int) {
	shadow(r, radius: 16)
	if let img = footage(key, inSec: 0, since: 0, t: Double(k) / FPS, step: step) {
		save {
			ctx.addPath(CGPath(roundedRect: r, cornerWidth: 16, cornerHeight: 16, transform: nil))
			ctx.clip()
			image(img, r)
		}
	}
	stroke(r, finished ? C("accent", 0.9) : C("line"), radius: 16, width: finished ? 3 : 1.5)
	chip(name, x: r.minX + 16, y: r.minY + 16, size: 20, alpha: 1)
	let row = hashes.isEmpty ? [] : hashes[min(hashes.count - 1, shownFrame / step)]
	if row.count >= 3 {
		let fr = (row[0] as? Int) ?? 0
		let h = (row[1 + i] as? String) ?? ""
		chip("frame \(String(format: "%04d", fr))  md5 \(h)", x: r.minX + 16, y: r.maxY - 58, size: 19, alpha: 1)
	}
}

func sceneVoice(_ o: Obj, _ t: Double) {
	let from = d(o, "from"), to = d(o, "to")
	let enter = outQuint(prog(t, from, 0.9))
	let out = inCubic(prog(t, to - 0.4, 0.4))
	let final = V ? CGRect(x: 0, y: 330, width: 1080, height: 608) : CGRect(x: 120, y: 236, width: 960, height: 540)
	// The card grows out of the determinism section's second card.
	let grow = inOutQuint(prog(t, from, 0.8))
	let card = lerpRect(detCards()[1], final, grow)
	let wave = V ? CGRect(x: 60, y: 1110, width: 960, height: 200) : CGRect(x: 1140, y: 360, width: 660, height: 260)
	let voiceAt = d(o, "voice_at"), voiceLen = d(o, "voice_len")
	save {
		setAlpha(1 - out)
		kicker(s(o, V ? "header_v" : "header"), t, at: from + 0.1, exit: to - 0.4)
		save {
			let radius = V ? lerp(16, 0, grow) : 16
			shadow(card, radius: radius)
			if let img = footage(s(o, "media"), inSec: d(o, "in"), since: d(o, "media_at"), t: min(max(t, d(o, "media_at")), d(o, "media_at") + d(o, "media_len", 1e9))) {
				save {
					ctx.addPath(CGPath(roundedRect: card, cornerWidth: radius, cornerHeight: radius, transform: nil))
					ctx.clip()
					image(img, card)
				}
			}
		}
		let la = outCubic(prog(t, from + 0.6, 0.4))
		if V { chip(s(o, "label"), x: 60, y: final.maxY + 20, size: 21, alpha: la) }
		else { chip(s(o, "label"), x: final.minX + 18, y: final.maxY - 64, size: 20, alpha: la) }
		let wa = outCubic(prog(t, from + 0.5, 0.7))
		var wr = wave
		wr.origin.y += (1 - wa) * 30
		save {
			setAlpha(wa)
			text(s(o, "line_id"), wr.minX, wr.minY - 74, font(32, .semibold, .mono), C("text"))
			text(s(o, "line_info"), wr.minX, wr.minY - 34, font(22, .regular, .mono), C("muted"))
			fill(wr, C("panel"), radius: 14)
			stroke(wr, C("line"), radius: 14)
			let peaks = (o["peaks"] as? [Double]) ?? []
			let ws = arr(o, "words")
			let inner = wr.insetBy(dx: 18, dy: 24)
			let n = peaks.count
			let play = CGFloat((t - voiceAt) / voiceLen)
			if n > 0 {
				let bw = inner.width / CGFloat(n)
				for (i, pk) in peaks.enumerated() {
					let x = inner.minX + CGFloat(i) * bw
					let fracX = CGFloat(i) / CGFloat(n)
					let hgt = max(2, CGFloat(pk) * inner.height)
					let growB = outCubic(prog(t, from + 0.6 + Double(fracX) * 0.5, 0.5))
					let hh = hgt * growB
					let heard = fracX <= play
					let tsec = Double(fracX) * voiceLen
					let inWord = ws.contains { tsec >= d($0, "start") && tsec <= d($0, "end") }
					let col = heard ? (inWord ? C("accent") : C("muted")) : (inWord ? C("text", 0.5) : C("dim"))
					fill(CGRect(x: x + bw * 0.15, y: inner.midY - hh / 2, width: max(1, bw * 0.7), height: hh), col, radius: min(bw * 0.35, 2))
				}
			}
			for w in ws {
				let x = inner.minX + inner.width * CGFloat(d(w, "start") / voiceLen)
				let lit = t >= voiceAt + d(w, "start")
				let pop = outCubic(prog(t, voiceAt + d(w, "start"), 0.18))
				fill(CGRect(x: x - 1, y: wr.maxY + 10, width: 2, height: 12 + pop * 8), lit ? C("accent") : C("dim"))
			}
			if let cut = o["cut"] as? Obj {
				let x = inner.minX + inner.width * CGFloat(d(cut, "at") / voiceLen)
				let lit = t >= voiceAt + d(cut, "at")
				save {
					ctx.setStrokeColor(lit ? C("accent") : C("muted"))
					ctx.setLineWidth(2)
					ctx.setLineDash(phase: 0, lengths: [6, 5])
					ctx.move(to: CGPoint(x: x, y: wr.minY - 6))
					ctx.addLine(to: CGPoint(x: x, y: wr.maxY + 6))
					ctx.strokePath()
				}
				let cf = font(20, .semibold, .mono)
				text(s(o, "cut_label"), x - 10, wr.minY + 30, cf, lit ? C("accent") : C("muted"), align: 1)
			}
			if play > 0 && play < 1 {
				let x = inner.minX + inner.width * play
				fill(CGRect(x: x - 1, y: wr.minY + 8, width: 2, height: wr.height - 16), C("text"))
			}
			text("0.00 s", wr.minX, wr.maxY + 56, font(20, .regular, .mono), C("muted"))
			text(String(format: "%.2f s", voiceLen), wr.maxX, wr.maxY + 56, font(20, .regular, .mono), C("muted"), align: 1)
		}
		let lines = termLines(o)
		let lr = V ? CGRect(x: 60, y: 1440, width: 960, height: 400) : CGRect(x: 120, y: 808, width: 1680, height: 236)
		let la2 = outCubic(prog(t, (lines.first?.at ?? to) - 0.3, 0.5))
		if la2 > 0 { terminal(lr, lines: lines, t: t, size: V ? 22 : 23, chrome: la2, title: s(o, "title"), alpha: la2) }
	}
}

/// The climb chart's best point, where the end card's pixels come from.
func bestPoint(_ o: Obj) -> CGPoint {
	let rounds = (o["rounds"] as? [[Any]]) ?? []
	let ch = V ? CGRect(x: 60, y: 1120, width: 960, height: 470) : CGRect(x: 950, y: 236, width: 850, height: 500)
	let plot = CGRect(x: ch.minX + 100, y: ch.minY + 140, width: ch.width - 160, height: ch.height - 220)
	let y0 = d(o, "y_min", 6.0), y1 = d(o, "y_max", 7.0)
	let best = rounds.map { ($0[1] as? Double) ?? 0 }.max() ?? y0
	return CGPoint(x: plot.maxX, y: plot.maxY - plot.height * CGFloat((best - y0) / (y1 - y0)))
}
func sceneReview(_ o: Obj, _ t: Double) {
	let from = d(o, "from"), to = d(o, "to")
	let out = inCubic(prog(t, to - 0.4, 0.4))
	let crit = (o["criteria"] as? [[Any]]) ?? []
	let rounds = (o["rounds"] as? [[Any]]) ?? []
	let enter = outQuint(prog(t, from, 0.9))
	save {
		setAlpha(1 - out)
		kicker(s(o, V ? "header_v" : "header"), t, at: from + 0.1, exit: to - 0.4)
		var card = V ? CGRect(x: 60, y: 360, width: 960, height: 700) : CGRect(x: 120, y: 236, width: 780, height: 790)
		card.origin.y += (1 - enter) * 50
		save {
			setAlpha(enter)
			shadow(card, radius: 18)
			fill(card, C("panel"), radius: 18)
			stroke(card, C("line"), radius: 18)
			text(s(o, "card_title"), card.minX + 36, card.minY + 60, font(28, .semibold, .mono), C("text"))
			text(s(o, "card_sub"), card.minX + 36, card.minY + 98, font(21, .regular, .mono), C("muted"))
			let rowH: CGFloat = V ? 50 : 56
			let top = card.minY + 130
			let barX = card.minX + (V ? 330 : 300), barW: CGFloat = V ? 480 : 330
			for (i, c) in crit.enumerated() {
				let name = (c[0] as? String) ?? ""
				let v = (c[1] as? Double) ?? Double((c[1] as? Int) ?? 0)
				let y = top + CGFloat(i) * rowH
				let p = outQuint(prog(t, from + 0.6 + Double(i) * 0.08, 0.8))
				text(name, card.minX + 36, y + 30, font(26, .medium), C("text"), alpha: clamp(p * 2))
				fill(CGRect(x: barX, y: y + 16, width: barW, height: 10), C("line"), radius: 5)
				fill(CGRect(x: barX, y: y + 16, width: barW * CGFloat(v / 10) * p, height: 10), v >= 7 ? C("accent") : C("muted"), radius: 5)
				text(String(format: "%.1f", v * Double(p)), card.maxX - 36, y + 31, font(26, .semibold, .mono), C("text"), align: 1, alpha: clamp(p * 2))
			}
			let y = top + CGFloat(crit.count) * rowH + 14
			fill(CGRect(x: card.minX + 36, y: y, width: card.width - 72, height: 1.2), C("line"))
			let ap = outCubic(prog(t, from + 1.6, 0.6))
			text(s(o, "average_label"), card.minX + 36, y + 66, font(28, .semibold), C("text"), alpha: ap)
			text(s(o, "pass_note"), card.minX + 36, y + 102, font(21, .regular, .mono), C("muted"), alpha: ap)
			text(s(o, "average"), card.maxX - 36, y + 86, font(72, .semibold, .mono), C("text"), align: 1, alpha: ap)
		}
		var ch = V ? CGRect(x: 60, y: 1120, width: 960, height: 470) : CGRect(x: 950, y: 236, width: 850, height: 500)
		let ce = outQuint(prog(t, from + 0.4, 0.9))
		ch.origin.y += (1 - ce) * 50
		save {
			setAlpha(ce)
			fill(ch, C("panel"), radius: 18)
			stroke(ch, C("line"), radius: 18)
			text(s(o, "chart_title"), ch.minX + 32, ch.minY + 58, font(28, .semibold, .mono), C("text"))
			text(s(o, "chart_sub"), ch.minX + 32, ch.minY + 94, font(21, .regular, .mono), C("muted"))
			let plot = CGRect(x: ch.minX + 100, y: ch.minY + 140, width: ch.width - 160, height: ch.height - 220)
			let y0 = d(o, "y_min", 6.0), y1 = d(o, "y_max", 7.0)
			func py(_ v: Double) -> CGFloat { plot.maxY - plot.height * CGFloat((v - y0) / (y1 - y0)) }
			func px(_ i: Int) -> CGFloat { plot.minX + plot.width * CGFloat(i) / CGFloat(max(rounds.count - 1, 1)) }
			for g in stride(from: y0, through: y1 + 1e-6, by: d(o, "y_step", 0.2)) {
				fill(CGRect(x: plot.minX, y: py(g), width: plot.width, height: 1), C("line"))
				text(String(format: "%.1f", g), plot.minX - 18, py(g) + 7, font(20, .regular, .mono), C("muted"), align: 1)
			}
			let pass = d(o, "pass", 7.0)
			save {
				ctx.setStrokeColor(C("text", 0.6))
				ctx.setLineWidth(2)
				ctx.setLineDash(phase: 0, lengths: [10, 8])
				ctx.move(to: CGPoint(x: plot.minX, y: py(pass)))
				ctx.addLine(to: CGPoint(x: plot.maxX, y: py(pass)))
				ctx.strokePath()
			}
			text(s(o, "pass_label"), plot.maxX, py(pass) - 14, font(20, .medium, .mono), C("text", 0.8), align: 1)
			for i in 0..<rounds.count { text("\(i + 1)", px(i), plot.maxY + 34, font(20, .regular, .mono), C("muted"), align: 0.5) }
			text(s(o, "x_label"), plot.minX, plot.maxY + 66, font(20, .regular, .mono), C("muted"))
			let start = from + 1.0, per = d(o, "per", 0.3)
			let shown = CGFloat((t - start) / per)
			var pts: [CGPoint] = []
			var best: [CGPoint] = []
			var b = -1.0
			for (i, rr) in rounds.enumerated() {
				let v = (rr[1] as? Double) ?? 0
				pts.append(CGPoint(x: px(i), y: py(v)))
				b = max(b, v)
				best.append(CGPoint(x: px(i), y: py(b)))
			}
			// The best so far as a step line: a change is kept only if the score rises.
			var stepPts: [CGPoint] = [best[0]]
			for i in 1..<best.count { stepPts.append(CGPoint(x: best[i].x, y: best[i - 1].y)); stepPts.append(best[i]) }
			let n = CGFloat(max(rounds.count - 1, 1))
			polyline(pts, clamp(shown / n), C("muted"), 2)
			polyline(stepPts, clamp(shown / n), C("accent"), 4)
			for (i, p) in pts.enumerated() {
				let a = outCubic(clamp(shown - CGFloat(i) + 1))
				if a <= 0 { continue }
				ctx.setFillColor(C("panel"))
				ctx.fillEllipse(in: CGRect(x: p.x - 7, y: p.y - 7, width: 14, height: 14))
				ctx.setStrokeColor(C("text", a))
				ctx.setLineWidth(2.5)
				ctx.strokeEllipse(in: CGRect(x: p.x - 6, y: p.y - 6, width: 12, height: 12))
			}
			let la = outCubic(prog(t, start + per * Double(rounds.count), 0.5))
			if let last = best.last, la > 0 {
				ctx.setFillColor(C("accent", la))
				ctx.fillEllipse(in: CGRect(x: last.x - 8, y: last.y - 8, width: 16, height: 16))
				text(s(o, "best_label"), last.x - 16, last.y - 24, font(22, .semibold, .mono), C("accent"), align: 1, alpha: la)
			}
		}
		let qa = outCubic(prog(t, d(o, "quote_at"), 0.7))
		if qa > 0 {
			var qy: CGFloat = V ? 1680 : 800
			qy += (1 - qa) * 20
			let qx: CGFloat = V ? 60 : 950
			let lines = s(o, V ? "quote_v" : "quote").components(separatedBy: "\n")
			for (i, l) in lines.enumerated() {
				text(l, qx, qy + CGFloat(i) * 44, font(V ? 32 : 31, .regular, italic: true), C("text"), alpha: qa)
			}
			text(s(o, "quote_by"), qx, qy + CGFloat(lines.count) * 44 + 14, font(21, .regular, .mono), C("muted"), alpha: qa)
		}
	}
}

func sceneEnd(_ o: Obj, _ t: Double) {
	let from = d(o, "from"), to = d(o, "to")
	let size: CGFloat = V ? 340 : 260
	let fade = 1 - inOutCubic(prog(t, to - 0.75, 0.75))
	// A slow push on the whole lockup while it holds.
	let push = 1 + 0.03 * inOutCubic(prog(t, from + 1.5, to - from - 1.5))
	let origin = ((J["scenes"] as? [Obj]) ?? []).first { s($0, "type") == "review" }.map(bestPoint)
	save {
		setAlpha(fade)
		ctx.translateBy(x: CW / 2, y: CH / 2)
		ctx.scaleBy(x: push, y: push)
		ctx.translateBy(x: -CW / 2, y: -CH / 2)
		let center = V ? CGPoint(x: CW / 2, y: 640) : CGPoint(x: CW / 2, y: 300)
		logo(CGPoint(x: center.x - size / 2, y: center.y - size / 2), size, t: t, at: from, assemble: true, from: origin)
		let nameY: CGFloat = V ? 960 : 556
		kinetic(s(o, "name"), x: CW / 2, baseline: nameY, size: V ? 128 : 108, weight: .semibold, color: C("text"),
			t: t, at: from + 1.0, stagger: 0, dur: 0.9, kern: -2.5)
		let tag = s(o, V ? "tagline_v" : "tagline").components(separatedBy: "\n")
		for (i, l) in tag.enumerated() {
			kinetic(l, x: CW / 2, baseline: nameY + (V ? 96 : 76) + CGFloat(i) * 58, size: V ? 46 : 38, weight: .regular,
				color: C("muted"), t: t, at: from + 1.35 + Double(i) * 0.1, stagger: 0.05)
		}
		let ua = outCubic(prog(t, from + 1.8, 0.6))
		let url = s(o, "url")
		let uf = font(V ? 34 : 32, .medium, .mono)
		let uy: CGFloat = V ? 1240 : 760
		let uw = width(url, uf)
		save {
			setAlpha(ua)
			let pill = CGRect(x: CW / 2 - uw / 2 - 32, y: uy - 48 + (1 - ua) * 14, width: uw + 64, height: 72)
			fill(pill, C("panel"), radius: 36)
			stroke(pill, C("accent", 0.7), radius: 36, width: 1.5)
			text(url, CW / 2, uy + (1 - ua) * 14, uf, C("text"), align: 0.5)
		}
		let run = s(o, "command")
		if !run.isEmpty {
			text(run, CW / 2, uy + (V ? 104 : 88), font(V ? 26 : 24, .regular, .mono), C("muted"), align: 0.5,
				alpha: outCubic(prog(t, from + 2.3, 0.6)))
		}
		let dis = s(o, V ? "disclaimer_v" : "disclaimer").components(separatedBy: "\n")
		for (i, l) in dis.enumerated() {
			text(l, CW / 2, (V ? 1470 : 950) + CGFloat(i) * 36, font(V ? 26 : 22, .regular), C("text", 0.6), align: 0.5,
				alpha: outCubic(prog(t, from + 2.8, 0.8)))
		}
	}
}

/// The chapter mark, top-left, on the canvas scenes: the small logo, a number and a word.
func chapters(_ t: Double) {
	for c in (J["chapters"] as? [Obj]) ?? [] {
		let a = outCubic(prog(t, d(c, "from"), 0.5)) * (1 - outCubic(prog(t, d(c, "to") - 0.35, 0.35)))
		if a <= 0 || t >= d(c, "to") || t < d(c, "from") { continue }
		let x: CGFloat = V ? 60 : 110, y: CGFloat = V ? 70 : 48
		save {
			setAlpha(a)
			logo(CGPoint(x: x, y: y), 34)
			text(s(c, "n"), x + 50, y + 24, font(18, .semibold, .mono), C("accent"))
			text(s(c, "text"), x + 86, y + 24, font(18, .regular, .mono), C("muted"))
		}
	}
}

func render(_ frame: Int) {
	let t = Double(frame) / FPS
	background()
	for sc in (J["scenes"] as? [Obj]) ?? [] {
		let from = d(sc, "from"), to = d(sc, "to")
		if t < from || t >= to { continue }
		switch s(sc, "type") {
		case "make": sceneMake(sc, t)
		case "title": sceneTitle(sc, t)
		case "footage": sceneFootage(sc, t)
		case "split": sceneSplit(sc, t)
		case "determinism": sceneDeterminism(sc, t)
		case "voice": sceneVoice(sc, t)
		case "review": sceneReview(sc, t)
		case "end": sceneEnd(sc, t)
		default: break
		}
	}
	chapters(t)
}

// MARK: - output

if let dir = arg("--png") {
	let at = (arg("--at") ?? "0").split(separator: ",").compactMap { Int($0) }
	for f in at {
		render(f)
		let img = ctx.makeImage()!
		let url = URL(fileURLWithPath: dir).appendingPathComponent(String(format: "f%05d.png", f))
		let dest = CGImageDestinationCreateWithURL(url as CFURL, UTType.png.identifier as CFString, 1, nil)!
		CGImageDestinationAddImage(dest, img, nil)
		CGImageDestinationFinalize(dest)
	}
	exit(0)
}
let first = Int(arg("--from") ?? "0") ?? 0
let last = Int(arg("--to") ?? String(FRAMES)) ?? FRAMES
let stdout = FileHandle.standardOutput
for f in first..<last {
	render(f)
	let data = Data(bytesNoCopy: ctx.data!, count: W * H * 4, deallocator: .none)
	stdout.write(data)
}
for r in readers.values { r.close() }
