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
import CoreImage
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
		// The command line, typed on, then the repository.
		let run = s(o, "command")
		let cf = font(V ? 38 : 40, .medium, .mono)
		let cy: CGFloat = V ? 1260 : 730
		let typedN = t < from + 1.8 ? 0 : min(run.count, Int((t - from - 1.8) * 30))
		if typedN > 0 || t >= from + 1.6 {
			let shown = String(run.prefix(typedN))
			let full = width(run, cf)
			let x0 = CW / 2 - full / 2
			if shown.hasPrefix("$") {
				let dw = text("$", x0, cy, cf, C("accent"))
				text(String(shown.dropFirst()), x0 + dw, cy, cf, C("text"))
			}
			if typedN < run.count || Int(t * 2) % 2 == 0 {
				fill(CGRect(x: x0 + width(shown, cf) + 4, y: cy - 32, width: 20, height: 40), C("accent", 0.9))
			}
		}
		let ua = outCubic(prog(t, from + 3.0, 0.6))
		let url = s(o, "url")
		let uf = font(V ? 32 : 30, .medium, .mono)
		let uy: CGFloat = V ? 1380 : 840
		let uw = width(url, uf)
		save {
			setAlpha(ua)
			let pill = CGRect(x: CW / 2 - uw / 2 - 32, y: uy - 46 + (1 - ua) * 14, width: uw + 64, height: 68)
			fill(pill, C("panel"), radius: 34)
			stroke(pill, C("accent", 0.7), radius: 34, width: 1.5)
			text(url, CW / 2, uy + (1 - ua) * 14, uf, C("text"), align: 0.5)
		}
		let dis = s(o, V ? "disclaimer_v" : "disclaimer").components(separatedBy: "\n")
		for (i, l) in dis.enumerated() {
			text(l, CW / 2, (V ? 1500 : 960) + CGFloat(i) * 36, font(V ? 26 : 22, .regular), C("text", 0.6), align: 0.5,
				alpha: outCubic(prog(t, from + 3.4, 0.8)))
		}
	}
}

// MARK: - the agent chat

/// Word-wraps proportional text to `maxW` points.
func wrapText(_ str: String, _ f: CTFont, _ maxW: CGFloat) -> [String] {
	var out: [String] = []
	var line = ""
	for w in str.split(separator: " ") {
		let cand = line.isEmpty ? String(w) : line + " " + w
		if width(cand, f) > maxW && !line.isEmpty { out.append(line); line = String(w) } else { line = cand }
	}
	if !line.isEmpty { out.append(line) }
	return out
}

struct ChatRow { let kind: String; let text: String; let at: Double; let h: CGFloat; let lineIdx: Int }
let chatRect = V ? CGRect(x: 40, y: 120, width: 1000, height: 1680) : CGRect(x: 210, y: 64, width: 1500, height: 952)
let chatSans = font(V ? 34 : 33, .regular), chatMono = font(V ? 22 : 24, .regular, .mono)
let promptH: CGFloat = V ? 150 : 112
let threadRect = CGRect(x: chatRect.minX + 40, y: chatRect.minY + 74, width: chatRect.width - 80,
	height: chatRect.height - 74 - promptH - 64)

/// The thread's rows at time `t`: the user's message, the agent's words, and its tool calls (command and output).
func chatRows(_ o: Obj) -> [ChatRow] {
	var rows: [ChatRow] = []
	let sent = d(o, "send_at")
	let userW = threadRect.width * 0.72
	for (i, l) in wrapText(s(o, "prompt"), chatSans, userW - 48).enumerated() {
		rows.append(ChatRow(kind: "user", text: l, at: sent, h: CTFontGetSize(chatSans) * 1.42, lineIdx: i))
	}
	rows.append(ChatRow(kind: "gap", text: "", at: sent, h: 26, lineIdx: 0))
	for m in arr(o, "messages") {
		let at = d(m, "t")
		if s(m, "kind") == "text" {
			rows.append(ChatRow(kind: "who", text: s(o, "agent_name"), at: at, h: 34, lineIdx: 0))
			for (i, l) in wrapText(s(m, "text"), chatSans, threadRect.width - 40).enumerated() {
				rows.append(ChatRow(kind: "agent", text: l, at: at + Double(i) * 0.25, h: CTFontGetSize(chatSans) * 1.42, lineIdx: i))
			}
			rows.append(ChatRow(kind: "gap", text: "", at: at, h: 18, lineIdx: 0))
		} else {
			let cols = Int((threadRect.width - 64) / width("M", chatMono))
			rows.append(ChatRow(kind: "tooltop", text: "", at: at, h: 22, lineIdx: 0))
			for (k, l) in arr(m, "lines").enumerated() {
				for (j, piece) in wrap(s(l, "text"), cols).enumerated() {
					let shown = (j > 0 && piece.hasPrefix("$ ")) ? " " + piece : piece
					rows.append(ChatRow(kind: "tool", text: shown, at: d(l, "t"), h: CTFontGetSize(chatMono) * 1.55, lineIdx: k))
				}
			}
			rows.append(ChatRow(kind: "toolbot", text: "", at: at, h: 22, lineIdx: 0))
			rows.append(ChatRow(kind: "gap", text: "", at: at, h: 18, lineIdx: 0))
		}
	}
	return rows
}
/// Where the focus row (the one the match-cut dives into) sits on screen at time t.
func chatFocus(_ o: Obj, _ t: Double) -> CGRect {
	let rows = chatRows(o)
	let (ys, _) = chatLayout(rows, t)
	let i = rows.lastIndex { $0.kind == "tool" && $0.text.contains(s(o, "focus")) } ?? rows.count - 1
	return CGRect(x: threadRect.minX + 32, y: ys[i], width: threadRect.width - 64, height: rows[i].h)
}
/// The y of every row: rows grow in as they appear, and the thread scrolls so the newest stays above the prompt box.
func chatLayout(_ rows: [ChatRow], _ t: Double) -> ([CGFloat], CGFloat) {
	var heights: [CGFloat] = []
	for r in rows { heights.append(r.h * outCubic(prog(t, r.at, 0.25))) }
	let total = heights.reduce(0, +)
	let scroll = max(0, total - threadRect.height)
	var ys: [CGFloat] = []
	// From the top, like any chat; once the thread is full it scrolls up under the header.
	var y = total < threadRect.height ? threadRect.minY + 10 : threadRect.maxY - total
	for h in heights { ys.append(y); y += h }
	return (ys, scroll)
}
func sceneChat(_ o: Obj, _ t: Double) {
	let cutAt = d(o, "cut_at")
	let z = inCubic(prog(t, cutAt, 0.6))
	let focus = chatFocus(o, min(t, cutAt))
	let fp = CGPoint(x: focus.midX, y: focus.midY)
	let rows = chatRows(o)
	let (ys, _) = chatLayout(rows, t)
	save {
		// The match-cut: the whole chat dives into the line where the hidden game starts recording.
		let k = 1 + z * 7
		ctx.translateBy(x: fp.x, y: fp.y)
		ctx.scaleBy(x: k, y: k)
		ctx.translateBy(x: -fp.x, y: -fp.y)
		setAlpha(1 - inCubic(prog(t, cutAt + 0.25, 0.35)))
		let enter = outQuint(prog(t, 0, 0.7))
		var win = chatRect
		win.origin.y += (1 - enter) * 30
		shadow(win, radius: 26, alpha: 0.55)
		fill(win, C("panel"), radius: 26)
		stroke(win, C("line"), radius: 26)
		// The header: a generic agent chat, no product's name or marks.
		fill(CGRect(x: win.minX + 28, y: win.minY + 28, width: 14, height: 14), C("accent"), radius: 7)
		text(s(o, "title"), win.minX + 54, win.minY + 42, font(V ? 24 : 21, .semibold, .mono), C("text"))
		text(s(o, "subtitle"), win.maxX - 28, win.minY + 42, font(V ? 22 : 19, .regular, .mono), C("muted"), align: 1)
		fill(CGRect(x: win.minX, y: win.minY + 64, width: win.width, height: 1.2), C("line"))
		// The thread.
		save {
			ctx.clip(to: CGRect(x: win.minX, y: win.minY + 66, width: win.width, height: threadRect.maxY - win.minY - 60))
			// Tool-call boxes first, under their lines; one still printing grows with it.
			var openTop: Int? = nil
			let visible = rows.indices.filter { t >= rows[$0].at }
			let lastBottom = visible.last.map { ys[$0] + rows[$0].h * outCubic(prog(t, rows[$0].at, 0.25)) } ?? 0
			for i in rows.indices {
				if rows[i].kind == "tooltop" && t >= rows[i].at { openTop = i }
				if rows[i].kind == "toolbot", let tp = openTop {
					let bottom = t >= rows[i].at ? ys[i] + 6 : lastBottom + 10
					let box = CGRect(x: threadRect.minX, y: ys[tp], width: threadRect.width, height: bottom - ys[tp])
					fill(box, CGColor(srgbRed: 0.075, green: 0.071, blue: 0.065, alpha: 1), radius: 16)
					stroke(box, C("line"), radius: 16)
					openTop = nil
				}
			}
			for (i, r) in rows.enumerated() where t >= r.at {
				let y = ys[i]
				let a = outCubic(prog(t, r.at, 0.25))
				switch r.kind {
				case "user":
					let lines = rows.filter { $0.kind == "user" }
					if r.lineIdx == 0 {
						let w = lines.map { width($0.text, chatSans) }.max()! + 48
						let h = CGFloat(lines.count) * r.h + 28
						let bub = CGRect(x: threadRect.maxX - w, y: y - 4 + (1 - a) * 40, width: w, height: h)
						fill(bub, C("panel2"), radius: 22)
						stroke(bub, C("line"), radius: 22)
					}
					let w = lines.map { width($0.text, chatSans) }.max()! + 48
					text(r.text, threadRect.maxX - w + 24, y + r.h * 0.82 + (1 - a) * 40, chatSans, C("text"), alpha: a)
				case "who":
					ctx.setFillColor(C("accent", a))
					ctx.fillEllipse(in: CGRect(x: threadRect.minX, y: y + 8, width: 14, height: 14))
					text(s(o, "agent_name"), threadRect.minX + 24, y + 21, font(V ? 21 : 19, .semibold, .mono), C("muted"), alpha: a)
				case "agent":
					// The agent's words arrive one at a time.
					let ws = r.text.split(separator: " ")
					let shown = min(ws.count, Int(max(0, (t - r.at) * 18)) + 1)
					text(ws.prefix(shown).joined(separator: " "), threadRect.minX, y + r.h * 0.8, chatSans, C("text"), alpha: a)
				case "tool":
					termLine(r.text, threadRect.minX + 32, y + r.h * 0.74, chatMono, alpha: a)
				default: break
				}
			}
		}
		// The prompt box, with its caret; the typed prompt leaves it on send.
		let pb = CGRect(x: win.minX + 28, y: win.maxY - promptH - 28, width: win.width - 56, height: promptH)
		fill(pb, C("panel2"), radius: 22)
		stroke(pb, t >= d(o, "type_at") && t < d(o, "send_at") ? C("text", 0.35) : C("line"), radius: 22, width: 1.5)
		let typeAt = d(o, "type_at"), sendAt = d(o, "send_at")
		let prompt = s(o, "prompt")
		let n = t < typeAt ? 0 : min(prompt.count, Int((t - typeAt) * d(o, "cps", 24)))
		let pf = font(V ? 34 : 30, .regular)
		let tx = pb.minX + 30
		if t < sendAt {
			let shown = String(prompt.prefix(n))
			let lines = n == 0 ? [] : wrapText(shown, pf, pb.width - 150)
			let base = pb.minY + (V ? 64 : 66)
			if lines.isEmpty {
				text(s(o, "placeholder"), tx, base, pf, C("dim"))
			}
			for (i, l) in lines.suffix(V ? 2 : 1).enumerated() { text(l, tx, base + CGFloat(i) * CTFontGetSize(pf) * 1.3, pf, C("text")) }
			let last = lines.suffix(V ? 2 : 1).last ?? ""
			let on = n < prompt.count && n > 0 || Int(t * 2) % 2 == 0
			if on {
				let cy = base + CGFloat(max(0, lines.suffix(V ? 2 : 1).count - 1)) * CTFontGetSize(pf) * 1.3
				fill(CGRect(x: tx + width(last, pf) + 3, y: cy - CTFontGetSize(pf) * 0.8, width: 3, height: CTFontGetSize(pf) * 1.0), C("accent"))
			}
		} else {
			text(s(o, "placeholder"), tx, pb.minY + (V ? 64 : 66), pf, C("dim"), alpha: outCubic(prog(t, sendAt + 0.3, 0.4)))
		}
		// The send button: lights when there is something to send, pulses on send.
		let sb = CGRect(x: pb.maxX - 82, y: pb.midY - 28, width: 56, height: 56)
		let ready = n > 0 && t < sendAt + 0.25
		let pulse = 1 + 0.12 * sin(.pi * prog(t, sendAt, 0.25))
		let sbr = sb.insetBy(dx: sb.width * (1 - pulse) / 2, dy: sb.height * (1 - pulse) / 2)
		ctx.setFillColor(ready ? C("accent") : C("dim"))
		ctx.fillEllipse(in: sbr)
		ctx.setStrokeColor(C("bg"))
		ctx.setLineWidth(4)
		ctx.setLineCap(.round)
		ctx.move(to: CGPoint(x: sb.midX, y: sb.midY + 12)); ctx.addLine(to: CGPoint(x: sb.midX, y: sb.midY - 12))
		ctx.move(to: CGPoint(x: sb.midX - 10, y: sb.midY - 2)); ctx.addLine(to: CGPoint(x: sb.midX, y: sb.midY - 12))
		ctx.addLine(to: CGPoint(x: sb.midX + 10, y: sb.midY - 2))
		ctx.strokePath()
	}
}

// MARK: - the hidden game, recording

/// A recording monitor over a take: REC and the frame counter (frames.csv), the script line that drives the shot, and
/// a top view of the camera's path and every actor (frames.csv, actors.csv), all on the frame shown.
func sceneMonitor(_ o: Obj, _ t: Double) {
	let clips = arr(o, "clips")
	guard let idx = clips.lastIndex(where: { t >= d($0, "at") }) else { return }
	let c = clips[idx]
	let at = d(c, "at"), dur = d(c, "dur")
	let step = Int(d(c, "step", 1))
	let key = V ? s(c, "media_v", s(c, "media")) : s(c, "media")
	let inSec = V ? d(c, "in_v", d(c, "in")) : d(c, "in")
	guard let img = footage(key, inSec: inSec, since: at, t: t, step: step) else { return }
	let full = CGRect(x: 0, y: 0, width: CW, height: CH)
	var r = full
	var radius: CGFloat = 0
	if s(c, "intro_from") == "chat", let chat = ((J["scenes"] as? [Obj]) ?? []).first(where: { s($0, "type") == "chat" }) {
		let f = chatFocus(chat, d(chat, "cut_at"))
		let p = inOutCubic(prog(t, at, d(c, "intro", 0.6)))
		let start = CGRect(x: f.midX - 80, y: f.midY - 45, width: 160, height: 90)
		r = lerpRect(start, full, p)
		radius = lerp(10, 0, p)
	}
	let z = lerp(1.0, CGFloat(d(c, "z1", 1.03)), CGFloat((t - at) / dur))
	save {
		ctx.addPath(CGPath(roundedRect: r, cornerWidth: radius, cornerHeight: radius, transform: nil))
		ctx.clip()
		image(img, r.insetBy(dx: -r.width * (z - 1) / 2, dy: -r.height * (z - 1) / 2))
	}
	let ha = outCubic(prog(t, d(clips[0], "at") + d(clips[0], "intro", 0) - 0.1, 0.35)) * (1 - outCubic(prog(t, d(o, "to") - 0.25, 0.25)))
	if ha <= 0 { return }
	let track = pick(c, "track")
	let frames = (track["f"] as? [Int]) ?? []
	let k = max(0, min(frames.count - 1, Int(((t - at) * 30 * Double(step)).rounded(.down))))
	save {
		setAlpha(ha)
		// REC, the shot and the frame counter, top-right.
		let rf = font(V ? 24 : 22, .semibold, .mono)
		let shot = s(c, "shot")
		let fr = frames.isEmpty ? 0 : frames[k]
		let total = Int(d(track, "n"))
		let line = String(format: "REC  %@  frame %04d / %04d  %.2f s", shot, fr, total, Double(fr) / 60)
		let w = width(line, rf) + 72
		let pill = V ? CGRect(x: CW - 60 - w, y: 96, width: w, height: 56) : CGRect(x: CW - 56 - w, y: 52, width: w, height: 56)
		fill(pill, CGColor(srgbRed: 0.05, green: 0.047, blue: 0.043, alpha: 0.82), radius: 28)
		stroke(pill, C("text", 0.12), radius: 28, width: 1.2)
		let blink = (Int((t - at) * 2) % 2 == 0) ? 1.0 : 0.35
		ctx.setFillColor(C("warn", CGFloat(blink)))
		ctx.fillEllipse(in: CGRect(x: pill.minX + 24, y: pill.midY - 8, width: 16, height: 16))
		text(line, pill.minX + 52, pill.midY + 8, rf, C("text"))
		text(s(o, "clock"), pill.maxX - 12, pill.maxY + 32, font(V ? 21 : 19, .regular, .mono), C("text", 0.75), align: 1)
		// The script line, top-left (bottom in the vertical, over the blurred fill).
		if V { footChip(clips, idx, t, x: 60, y: 1330, alpha: 1) } else { footChip(clips, idx, t, x: 56, y: 52, alpha: 1) }
		// The top view.
		let m = V ? CGRect(x: CW - 60 - 330, y: 210, width: 330, height: 300) : CGRect(x: CW - 56 - 300, y: 150, width: 300, height: 264)
		fill(m, CGColor(srgbRed: 0.05, green: 0.047, blue: 0.043, alpha: 0.82), radius: 16)
		stroke(m, C("text", 0.12), radius: 16, width: 1.2)
		text(s(o, "map_title"), m.minX + 18, m.minY + 30, font(V ? 19 : 17, .medium, .mono), C("muted"))
		let b = (track["b"] as? [Double]) ?? [0, 0, 1, 1]
		let area = m.insetBy(dx: 22, dy: 22).offsetBy(dx: 0, dy: 16).insetBy(dx: 0, dy: 8)
		let sx = area.width / CGFloat(b[2] - b[0]), sz = area.height / CGFloat(b[3] - b[1])
		let sc = min(sx, sz)
		let ox = area.midX - CGFloat(b[0] + b[2]) / 2 * sc, oz = area.midY - CGFloat(b[1] + b[3]) / 2 * sc
		func P(_ x: Double, _ zz: Double) -> CGPoint { CGPoint(x: ox + CGFloat(x) * sc, y: oz + CGFloat(zz) * sc) }
		let cam = (track["c"] as? [[Double]]) ?? []
		save {
			ctx.clip(to: m.insetBy(dx: 4, dy: 4))
			if cam.count > 1 {
				polyline(cam.map { P($0[0], $0[1]) }, 1, C("text", 0.22), 2)
				if k > 0 { polyline(cam.prefix(k + 1).map { P($0[0], $0[1]) }, 1, C("accent"), 3) }
			}
			// Actors: a trail for the ones that move, a dot for each.
			for a in (track["a"] as? [Obj]) ?? [] {
				let ps = (a["p"] as? [[Double]]) ?? []
				if ps.isEmpty { continue }
				let kk = min(k, ps.count - 1)
				if kk > 0 { polyline(ps.prefix(kk + 1).map { P($0[0], $0[1]) }, 1, C("text", 0.5), 2) }
				let p = P(ps[kk][0], ps[kk][1])
				ctx.setFillColor(C("text"))
				ctx.fillEllipse(in: CGRect(x: p.x - 5, y: p.y - 5, width: 10, height: 10))
			}
			if !cam.isEmpty {
				let cp = cam[min(k, cam.count - 1)]
				let p = P(cp[0], cp[1])
				let yaw = CGFloat(cp[2]) * .pi / 180
				let dir = CGPoint(x: -sin(yaw), y: cos(yaw))
				let side = CGPoint(x: -dir.y, y: dir.x)
				ctx.setFillColor(C("accent"))
				ctx.move(to: CGPoint(x: p.x + dir.x * 16, y: p.y + dir.y * 16))
				ctx.addLine(to: CGPoint(x: p.x - dir.x * 7 + side.x * 9, y: p.y - dir.y * 7 + side.y * 9))
				ctx.addLine(to: CGPoint(x: p.x - dir.x * 7 - side.x * 9, y: p.y - dir.y * 7 - side.y * 9))
				ctx.closePath()
				ctx.fillPath()
			}
		}
		text(s(o, "map_legend"), m.minX + 18, m.maxY - 14, font(V ? 17 : 15, .regular, .mono), C("muted"))
	}
}

// MARK: - the edit

func sceneTimeline(_ o: Obj, _ t: Double) {
	let from = d(o, "from"), to = d(o, "to")
	let out = inCubic(prog(t, to - 0.4, 0.4))
	let enter = outQuint(prog(t, from, 0.8))
	let total = d(o, "seconds")
	let scrubAt = d(o, "scrub_at"), scrubDur = d(o, "scrub_dur")
	let ph = clamp(CGFloat((t - scrubAt) / scrubDur)) * CGFloat(total)
	save {
		setAlpha(1 - out)
		kicker(s(o, V ? "header_v" : "header"), t, at: from + 0.1, exit: to - 0.4)
		// The program monitor: the film at the playhead.
		let mon = V ? CGRect(x: 60, y: 330, width: 960, height: 540) : CGRect(x: 1080, y: 236, width: 720, height: 405)
		var mr = mon
		mr.origin.y += (1 - enter) * 40
		save {
			setAlpha(enter)
			shadow(mr, radius: 14)
			if let img = footage(s(o, "media"), inSec: 0, since: 0, t: Double(ph) * 60 / Double(d(o, "step", 15)) / FPS, step: Int(d(o, "step", 15))) {
				save {
					ctx.addPath(CGPath(roundedRect: mr, cornerWidth: 14, cornerHeight: 14, transform: nil))
					ctx.clip()
					image(img, mr)
				}
			}
			stroke(mr, C("line"), radius: 14)
			chip(String(format: "%@  %05.2f s", s(o, "media_label"), Double(ph)), x: mr.minX + 14, y: mr.minY + 14, size: 18, alpha: 1)
		}
		// Facts, left of the monitor (above it in the vertical).
		let fx: CGFloat = V ? 60 : 120, fy: CGFloat = V ? 940 : 300
		for (i, l) in s(o, "facts").components(separatedBy: "\n").enumerated() {
			let a = outCubic(prog(t, from + 0.3 + Double(i) * 0.12, 0.5))
			text(l, fx, fy + CGFloat(i) * 46, font(i == 0 ? 30 : 26, i == 0 ? .semibold : .regular, .mono), i == 0 ? C("text") : C("muted"), alpha: a)
		}
		// The tracks.
		let tr = V ? CGRect(x: 60, y: 1180, width: 960, height: 560) : CGRect(x: 120, y: 690, width: 1680, height: 330)
		let lab: CGFloat = V ? 110 : 120
		let lane = CGRect(x: tr.minX + lab, y: tr.minY, width: tr.width - lab, height: tr.height)
		func X(_ sec: Double) -> CGFloat { lane.minX + lane.width * CGFloat(sec / total) }
		let names = ["video", "voice", "music", "sfx"]
		let laneH: CGFloat = V ? 110 : 64, gap: CGFloat = V ? 26 : 14
		let top = tr.minY + 40
		func laneY(_ i: Int) -> CGFloat { top + CGFloat(i) * (laneH + gap) }
		save {
			setAlpha(enter)
			// The ruler.
			for sec in stride(from: 0, through: total, by: 10) {
				fill(CGRect(x: X(sec), y: tr.minY + 12, width: 1.2, height: 14), C("dim"))
				text("\(Int(sec)) s", X(sec) + 6, tr.minY + 24, font(17, .regular, .mono), C("muted"))
			}
			for (i, n) in names.enumerated() {
				text(n, tr.minX, laneY(i) + laneH / 2 + 7, font(V ? 22 : 20, .medium, .mono), C("muted"))
				fill(CGRect(x: lane.minX, y: laneY(i), width: lane.width, height: laneH), C("panel"), radius: 8)
			}
			// Video: the clips slide into the track from the right, one after another.
			let clips = (o["clips"] as? [[Any]]) ?? []
			let slideAt = d(o, "slide_at")
			for (i, cl) in clips.enumerated() {
				let st = (cl[0] as? Double) ?? 0, du = (cl[1] as? Double) ?? 0, name = (cl[2] as? String) ?? "", kind = (cl[3] as? String) ?? "shot"
				let p = outQuint(prog(t, slideAt + Double(i) * 0.05, 0.55))
				if p <= 0 { continue }
				var r = CGRect(x: X(st) + 1, y: laneY(0) + 4, width: max(2, X(st + du) - X(st) - 2), height: laneH - 8)
				r.origin.x += (1 - p) * 260
				let shotC = i % 2 == 0 ? C("panel2") : mix(C("panel2"), C("line"), 0.6)
				fill(r, kind == "black" ? C("bg") : shotC, radius: 5)
				stroke(r, kind == "black" ? C("line") : mix(C("line"), C("accent", 0.6), 0.25), radius: 5, width: 1.2)
				if r.width > 66 && !V {
					save { ctx.clip(to: r.insetBy(dx: 4, dy: 0)); text(name, r.minX + 8, r.midY + 6, font(15, .regular, .mono), C("text", 0.8)) }
				}
			}
			// Voice lines, then the music bed's level (ducked under every line), then every sound effect.
			let la = outCubic(prog(t, d(o, "lanes_at"), 0.5))
			let voice = (o["voice"] as? [[Double]]) ?? []
			for (i, v) in voice.enumerated() {
				let p = outCubic(prog(t, d(o, "lanes_at") + Double(i) * 0.02, 0.3))
				if p <= 0 { continue }
				let r = CGRect(x: X(v[0]), y: laneY(1) + laneH * (0.5 - 0.36 * p), width: max(2, X(v[0] + v[1]) - X(v[0])), height: laneH * 0.72 * p)
				fill(r, C("accent", 0.75), radius: 4)
			}
			if la > 0 {
				let duck = d(o, "duck_db", -9)
				var pts: [CGPoint] = []
				let n = 600
				for j in 0...n {
					let sec = total * Double(j) / Double(n)
					let under = voice.contains { sec >= $0[0] - 0.03 && sec <= $0[0] + $0[1] + 0.2 }
					let db = under ? duck : 0
					pts.append(CGPoint(x: X(sec), y: laneY(2) + 10 + (laneH - 20) * CGFloat(-db / 14)))
				}
				polyline(pts, la, C("text", 0.8), 2)
				for cue in (o["music_cues"] as? [[Any]]) ?? [] {
					let sec = (cue[0] as? Double) ?? 0
					fill(CGRect(x: X(sec) - 1, y: laneY(2) + laneH - 10, width: 2, height: 8), C("muted", la))
				}
				text(String(format: "bed %.0f dB under every line", duck), lane.maxX - 8, laneY(2) + laneH - 10, font(15, .regular, .mono), C("muted"), align: 1, alpha: la)
				for sec in (o["sfx"] as? [Double]) ?? [] {
					fill(CGRect(x: X(sec) - 1, y: laneY(3) + 12, width: 2, height: laneH - 24), C("text", 0.55 * la))
				}
			}
			// Cuts on words: when the playhead reaches one, its marker snaps to the word's onset.
			for cut in (o["cuts"] as? [[Any]]) ?? [] {
				let sec = (cut[0] as? Double) ?? 0, word = (cut[1] as? String) ?? ""
				let p = outCubic(prog(t, scrubAt + scrubDur * sec / total, 0.3))
				if p <= 0 { continue }
				let x = X(sec) + (1 - settle(prog(t, scrubAt + scrubDur * sec / total, 0.35))) * 14
				fill(CGRect(x: x - 1.5, y: laneY(0) - 6, width: 3, height: laneY(1) + laneH + 6 - laneY(0) + 6), C("accent", p))
				let f = font(V ? 20 : 17, .semibold, .mono)
				let label = "cut on " + word
				let lw = width(label, f) + 20
				let tag = CGRect(x: x - lw / 2, y: laneY(0) - 40, width: lw, height: 30)
				fill(tag, C("accent", p), radius: 15)
				text(label, x, tag.midY + 6, f, C("bg"), align: 0.5, alpha: p)
			}
			// The playhead.
			if t >= scrubAt {
				let x = X(Double(ph))
				fill(CGRect(x: x - 1, y: tr.minY + 30, width: 2, height: laneY(3) + laneH - tr.minY - 26), C("text"))
				ctx.setFillColor(C("text"))
				ctx.move(to: CGPoint(x: x - 8, y: tr.minY + 26)); ctx.addLine(to: CGPoint(x: x + 8, y: tr.minY + 26))
				ctx.addLine(to: CGPoint(x: x, y: tr.minY + 38)); ctx.closePath(); ctx.fillPath()
			}
		}
	}
}

// MARK: - Minecraft's own GUI: font, sprites, screens (read at render time from the local game jar, never committed)


/// One GUI pixel in frame pixels: GUI scale 4, the game's own at 1080 lines (a 480x270 GUI on 1920x1080, 270x480 on 1080x1920).
let G: CGFloat = 4
let MCROOT = (J["mc"] as? String) ?? ""
var pngCache: [String: CGImage] = [:]
func png(_ rel: String) -> CGImage? {
	if let i = pngCache[rel] { return i }
	let url = URL(fileURLWithPath: MCROOT + "/" + rel) as CFURL
	guard let src = CGImageSourceCreateWithURL(url, nil), let img = CGImageSourceCreateImageAtIndex(src, 0, nil) else { return nil }
	pngCache[rel] = img
	return img
}
/// Draws an image with nearest-neighbour sampling (pixel-crisp), flipped for the top-left canvas.
func blit(_ img: CGImage, _ r: CGRect, alpha: CGFloat = 1) {
	save {
		ctx.interpolationQuality = .none
		setAlpha(alpha)
		ctx.translateBy(x: r.minX, y: r.maxY)
		ctx.scaleBy(x: 1, y: -1)
		ctx.draw(img, in: CGRect(x: 0, y: 0, width: r.width, height: r.height))
	}
}
/// A GUI sprite (textures/gui/sprites/<name>.png), nine-sliced by its .mcmeta border, at GUI scale.
struct Slice { let l: Int; let t: Int; let r: Int; let b: Int }
var sliceCache: [String: Slice?] = [:]
func sliceOf(_ name: String) -> Slice? {
	if let s = sliceCache[name] { return s }
	var out: Slice? = nil
	if let data = FileManager.default.contents(atPath: MCROOT + "/gui/sprites/\(name).png.mcmeta"),
		let j = try? JSONSerialization.jsonObject(with: data) as? Obj, let gui = j["gui"] as? Obj, let sc = gui["scaling"] as? Obj,
		s(sc, "type") == "nine_slice" {
		if let b = sc["border"] as? Int { out = Slice(l: b, t: b, r: b, b: b) }
		else if let b = sc["border"] as? Obj { out = Slice(l: Int(d(b, "left")), t: Int(d(b, "top")), r: Int(d(b, "right")), b: Int(d(b, "bottom"))) }
	}
	sliceCache[name] = out
	return out
}
func sprite(_ name: String, _ r: CGRect, alpha: CGFloat = 1) {
	guard let img = png("gui/sprites/\(name).png") else { return }
	guard let sl = sliceOf(name) else { blit(img, r, alpha: alpha); return }
	let w = CGFloat(img.width), h = CGFloat(img.height)
	let L = CGFloat(sl.l), T = CGFloat(sl.t), R = CGFloat(sl.r), B = CGFloat(sl.b)
	let xs: [(CGFloat, CGFloat, CGFloat, CGFloat)] = [(0, L, r.minX, L * G), (L, w - L - R, r.minX + L * G, r.width - (L + R) * G), (w - R, R, r.maxX - R * G, R * G)]
	let ys: [(CGFloat, CGFloat, CGFloat, CGFloat)] = [(0, T, r.minY, T * G), (T, h - T - B, r.minY + T * G, r.height - (T + B) * G), (h - B, B, r.maxY - B * G, B * G)]
	for (sx, sw, dx, dw) in xs {
		for (sy, sh, dy, dh) in ys where sw > 0 && sh > 0 && dw > 0 && dh > 0 {
			if let part = img.cropping(to: CGRect(x: sx, y: sy, width: sw, height: sh)) {
				blit(part, CGRect(x: dx, y: dy, width: dw, height: dh), alpha: alpha)
			}
		}
	}
}
/// Snaps a frame coordinate to the GUI pixel grid.
func snap(_ v: CGFloat) -> CGFloat { (v / G).rounded() * G }

// The font: the game's bitmap providers (ascii.png, nonlatin_european.png), glyph widths from their pixels.
struct Glyph { let sheet: String; let rect: CGRect; let adv: CGFloat }
var glyphs: [Character: Glyph] = [:]
var fontReady = false
func loadFont() {
	fontReady = true
	guard let data = FileManager.default.contents(atPath: MCROOT + "/../font/include/default.json"),
		let j = try? JSONSerialization.jsonObject(with: data) as? Obj else { return }
	for p in arr(j, "providers") where s(p, "type") == "bitmap" {
		let file = s(p, "file").replacingOccurrences(of: "minecraft:", with: "")
		guard file == "font/ascii.png" || file == "font/nonlatin_european.png", let img = png(file),
			let rows = p["chars"] as? [String] else { continue }
		let cw = img.width / 16, ch = img.height / rows.count
		// Read the alpha to find each glyph's width (the rightmost lit column), as the game does.
		let bpr = img.width * 4
		var px = [UInt8](repeating: 0, count: bpr * img.height)
		let c2 = CGContext(data: &px, width: img.width, height: img.height, bitsPerComponent: 8, bytesPerRow: bpr, space: cs,
			bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
		c2.draw(img, in: CGRect(x: 0, y: 0, width: img.width, height: img.height))
		for (ri, row) in rows.enumerated() {
			for (ci, chr) in row.enumerated() where glyphs[chr] == nil {
				var right = -1
				for x in 0..<cw { for y in 0..<ch where px[(ri * ch + y) * bpr + (ci * cw + x) * 4 + 3] > 0 { right = max(right, x) } }
				if chr == " " { continue }
				glyphs[chr] = Glyph(sheet: file, rect: CGRect(x: ci * cw, y: ri * ch, width: cw, height: ch), adv: CGFloat(right + 2))
			}
		}
	}
}
var tinted: [String: CGImage] = [:]
func tintedSheet(_ sheet: String, _ color: CGColor) -> CGImage? {
	let c = color.components!
	let key = "\(sheet)#\(c[0])-\(c[1])-\(c[2])"
	if let i = tinted[key] { return i }
	guard let img = png(sheet) else { return nil }
	let c2 = CGContext(data: nil, width: img.width, height: img.height, bitsPerComponent: 8, bytesPerRow: img.width * 4, space: cs,
		bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
	c2.draw(img, in: CGRect(x: 0, y: 0, width: img.width, height: img.height))
	c2.setBlendMode(.sourceIn)
	c2.setFillColor(CGColor(srgbRed: c[0], green: c[1], blue: c[2], alpha: 1))
	c2.fill(CGRect(x: 0, y: 0, width: img.width, height: img.height))
	let out = c2.makeImage()!
	tinted[key] = out
	return out
}
/// The game's text colours (§ codes).
let MCCOL: [Character: String] = ["0": "#000000", "1": "#0000AA", "2": "#00AA00", "3": "#00AAAA", "4": "#AA0000", "5": "#AA00AA",
	"6": "#FFAA00", "7": "#AAAAAA", "8": "#555555", "9": "#5555FF", "a": "#55FF55", "b": "#55FFFF", "c": "#FF5555",
	"d": "#FF55FF", "e": "#FFFF55", "f": "#FFFFFF", "y": "#FFE23B", "k": "#10141A"]
func plain(_ str: String) -> String {
	var out = ""
	var skip = false
	for ch in str { if skip { skip = false; continue }; if ch == "§" { skip = true; continue }; out.append(ch) }
	return out
}
/// Width of a string in frame pixels at `k` GUI pixels per font pixel.
func mcWidth(_ str: String, _ k: CGFloat = 1) -> CGFloat {
	if !fontReady { loadFont() }
	var w: CGFloat = 0
	for ch in plain(str) { w += (ch == " " ? 4 : (glyphs[ch]?.adv ?? 6)) }
	return (w - 1) * G * k
}
enum MCStyle { case flat, shadow, outline }
/// Draws game-font text with its top-left at (x, y); `k` is the size in GUI pixels per font pixel. `shadow` is the GUI's
/// own drop shadow; `outline` is the caption look (an ink outline and a 2-pixel drop, the in-game text layer's style).
@discardableResult
func mcText(_ str: String, _ x: CGFloat, _ y: CGFloat, k: CGFloat = 1, color: String = "#FFFFFF", style: MCStyle = .shadow,
	alpha: CGFloat = 1, align: CGFloat = 0) -> CGFloat {
	if !fontReady { loadFont() }
	let px = G * k
	let w = mcWidth(str, k)
	let x0 = snap(x - w * align), y0 = snap(y)
	func pass(_ dx: CGFloat, _ dy: CGFloat, _ fixed: CGColor?) {
		var cx = x0 + dx
		var col = hex(color)
		var code = false
		for ch in str {
			if code { if let c = MCCOL[ch] { col = hex(c) }; code = false; continue }
			if ch == "§" { code = true; continue }
			if ch == " " { cx += 4 * px; continue }
			guard let g = glyphs[ch] else { cx += 6 * px; continue }
			var use = fixed ?? col
			if fixed == nil, style == .shadow { use = col }
			if let sheet = tintedSheet(g.sheet, use), let part = sheet.cropping(to: g.rect) {
				blit(part, CGRect(x: cx, y: y0 + dy - px, width: g.rect.width * px, height: g.rect.height * px), alpha: alpha)
			}
			cx += g.adv * px
		}
	}
	switch style {
	case .flat: pass(0, 0, nil)
	case .shadow:
		// The GUI's drop shadow: the colour at a quarter brightness, one pixel down and right.
		passShadow(str, x0, y0, px, alpha)
		pass(0, 0, nil)
	case .outline:
		let ink = hex("#10141A")
		for (ox, oy) in [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, -1), (-1, 1), (1, 1)] { pass(CGFloat(ox) * px, CGFloat(oy) * px, ink) }
		pass(0, 2 * px, ink)
		pass(0, 0, nil)
	}
	return w
}
func passShadow(_ str: String, _ x0: CGFloat, _ y0: CGFloat, _ px: CGFloat, _ alpha: CGFloat) {
	var cx = x0 + px
	var col = hex("#FFFFFF")
	var code = false
	for ch in str {
		if code { if let c = MCCOL[ch] { col = hex(c) }; code = false; continue }
		if ch == "§" { code = true; continue }
		if ch == " " { cx += 4 * px; continue }
		guard let g = glyphs[ch] else { cx += 6 * px; continue }
		let c = col.components!
		let sh = CGColor(srgbRed: c[0] * 0.25, green: c[1] * 0.25, blue: c[2] * 0.25, alpha: 1)
		if let sheet = tintedSheet(g.sheet, sh), let part = sheet.cropping(to: g.rect) {
			blit(part, CGRect(x: cx, y: y0, width: g.rect.width * px, height: g.rect.height * px), alpha: alpha)
		}
		cx += g.adv * px
	}
}
/// Words of game text, wrapped to `maxW` frame pixels (colour codes carry over a wrap).
func mcWrap(_ str: String, _ maxW: CGFloat, _ k: CGFloat = 1) -> [String] {
	var out: [String] = []
	var line = ""
	for w in str.split(separator: " ", omittingEmptySubsequences: false) {
		let cand = line.isEmpty ? String(w) : line + " " + w
		if mcWidth(cand, k) > maxW && !line.isEmpty { out.append(line); line = "  " + w } else { line = cand }
	}
	out.append(line)
	return out
}
/// CLI output in the game's colours: the line's first word dark grey, verdicts green, failures red, the rest grey.
func mcTerm(_ str: String) -> String {
	if str.hasPrefix("$ ") { return "§8$ §f" + String(str.dropFirst(2)) }
	if str.hasPrefix("  ") { return "§8" + str }
	var out: [String] = []
	for (i, p) in str.split(separator: " ", omittingEmptySubsequences: false).enumerated() {
		let w = String(p)
		if ["PASS", "ok", "locked", "READY"].contains(w) { out.append("§a" + w + "§7") }
		else if w == "FAIL" { out.append("§c" + w + "§7") }
		else if i == 0 && w == w.uppercased() && w.count >= 3 && (w.first?.isLetter ?? false) { out.append("§8" + w + "§7") }
		else { out.append(w) }
	}
	return "§7" + out.joined(separator: " ")
}

// The menu screen: the world behind blurred (as the game blurs it under a screen), the in-world menu background over
// it, and the header and footer separators.
let ciContext = CIContext(options: [.useSoftwareRenderer: false])
func blurred(_ img: CGImage, _ radius: CGFloat) -> CGImage? {
	let ci = CIImage(cgImage: img).clampedToExtent().applyingGaussianBlur(sigma: Double(radius))
	return ciContext.createCGImage(ci, from: CGRect(x: 0, y: 0, width: img.width, height: img.height))
}
func tile(_ rel: String, _ r: CGRect, alpha: CGFloat = 1) {
	guard let img = png(rel) else { return }
	let tw = CGFloat(img.width) * G, th = CGFloat(img.height) * G
	save {
		ctx.clip(to: r)
		var y = r.minY
		while y < r.maxY { var x = r.minX; while x < r.maxX { blit(img, CGRect(x: x, y: y, width: tw, height: th), alpha: alpha); x += tw }; y += th }
	}
}
/// The world behind a screen: a frame of `key` at time t, cover-fitted, blurred, then the menu background over it.
func menuBackdrop(_ key: String, inSec: Double, since: Double, t: Double, header: CGFloat, footer: CGFloat) {
	if let img = footage(key, inSec: inSec, since: since, t: t) {
		let a = CGFloat(img.width) / CGFloat(img.height)
		var r = CGRect(x: 0, y: 0, width: CW, height: CH)
		if a > CW / CH { let w = CH * a; r = CGRect(x: (CW - w) / 2, y: 0, width: w, height: CH) }
		else { let h = CW / a; r = CGRect(x: 0, y: (CH - h) / 2, width: CW, height: h) }
		if let b = blurred(img, 14) { image(b, r) } else { image(img, r) }
	}
	tile("gui/inworld_menu_background.png", CGRect(x: 0, y: 0, width: CW, height: CH))
	tile("gui/inworld_menu_list_background.png", CGRect(x: 0, y: header, width: CW, height: footer - header))
	tile("gui/inworld_header_separator.png", CGRect(x: 0, y: header - 2 * G, width: CW, height: 2 * G))
	tile("gui/inworld_footer_separator.png", CGRect(x: 0, y: footer, width: CW, height: 2 * G))
}
/// The game's translucent black panel (chat lines, the in-game overlays).
func mcPanel(_ r: CGRect, _ a: CGFloat = 0.55) { fill(CGRect(x: snap(r.minX), y: snap(r.minY), width: snap(r.width), height: snap(r.height)), CGColor(gray: 0, alpha: a)) }
/// A tooltip: its own background and purple frame sprites.
func mcTooltip(_ r: CGRect, alpha: CGFloat = 1) {
	let rr = CGRect(x: snap(r.minX), y: snap(r.minY), width: snap(r.width), height: snap(r.height))
	sprite("tooltip/background", rr, alpha: alpha)
	sprite("tooltip/frame", rr, alpha: alpha)
}

// MARK: - the Minecraft-native scenes (GUI scale 4, the game's font, vanilla chrome only; footage always full frame)

/// The frame in GUI pixels.
let GW = CW / G, GH = CH / G
/// Text size: the GUI's own size in the landscape cut; doubled in the vertical so capitals clear 44 px on a phone.
let TK: CGFloat = V ? 2 : 1
func gx(_ v: CGFloat) -> CGFloat { v * G }

/// Full-frame footage, cover-fitted (the vertical cut plays the tool's own 9:16 re-frame when the clip names one).
func fullFrame(_ c: Obj, _ t: Double, since: Double, step: Int = 1, speed: Double = 1) {
	let key = V ? s(c, "media_v", s(c, "media")) : s(c, "media")
	let inSec = V && c["media_v"] != nil ? d(c, "in_v", d(c, "in")) : d(c, "in")
	guard let img = footage(key, inSec: inSec, since: since, t: since + (t - since) * speed, step: step) else { return }
	placeFrame(img, fx: CGFloat(d(c, "fx", 0.5)))
}
/// A frame full frame: cover-fitted, or in the vertical cut a landscape frame whole over a blurred fill of itself.
func placeFrame(_ img: CGImage, fx: CGFloat = 0.5, band: Bool = false) {
	let a = CGFloat(img.width) / CGFloat(img.height)
	var r = CGRect(x: 0, y: 0, width: CW, height: CH)
	if V && a > 1.2 && !band {
		// A landscape take in the vertical cut, re-framed: a full-height crop centred on `fx` of the source's width
		// (only takes with no text in them come this way; captioned takes have true 9:16 re-shoots).
		let w = CH * a
		let x = clamp(-(w * fx - CW / 2), CW - w, 0)
		image(img, CGRect(x: x, y: 0, width: w, height: CH))
		return
	}
	if V && a > 1.2 {
		// A landscape take in the vertical cut: whole and full width (its captions intact) over a blurred fill of
		// itself, the way the tool's own 9:16 re-frame lays out a clip whose text would not fit a crop.
		let w = CH * a
		if let b = blurred(img, 18) { image(b, CGRect(x: (CW - w) / 2, y: 0, width: w, height: CH)) }
		fill(CGRect(x: 0, y: 0, width: CW, height: CH), CGColor(gray: 0, alpha: 0.25))
		let h = CW / a
		image(img, CGRect(x: 0, y: (CH - h) / 2, width: CW, height: h))
		return
	}
	if a > CW / CH { let w = CH * a; r = CGRect(x: (CW - w) / 2, y: 0, width: w, height: CH) }
	else if a < CW / CH { let h = CW / a; r = CGRect(x: 0, y: (CH - h) / 2, width: CW, height: h) }
	image(img, r)
}

/// Darkens the picture under type.
func dim(_ a: CGFloat) { if a > 0 { fill(CGRect(x: 0, y: 0, width: CW, height: CH), CGColor(gray: 0, alpha: a)) } }
/// A soft dark gradient from one edge (`top`) so type over footage reads without a box.
func scrim(top: Bool, depth: CGFloat, alpha: CGFloat) {
	if alpha <= 0 { return }
	let g = CGGradient(colorsSpace: cs, colors: [CGColor(gray: 0, alpha: alpha), CGColor(gray: 0, alpha: 0)] as CFArray, locations: [0, 1])!
	let y0 = top ? 0 : CH, y1 = top ? depth : CH - depth
	ctx.drawLinearGradient(g, start: CGPoint(x: 0, y: y0), end: CGPoint(x: 0, y: y1), options: [])
}
/// A heading in the trailer's type over footage (the chapter beats: "Then it edits."), the picture dimmed under it
/// while it is up. Returns how far it is up (0-1).
@discardableResult
func heading(_ o: Obj, _ t: Double) -> CGFloat {
	let from = d(o, "from"), until = d(o, "heading_until", 0)
	let txt = s(o, V ? "heading_v" : "heading", s(o, "heading"))
	if txt.isEmpty || t >= until + 0.6 { return 0 }
	let up = outCubic(prog(t, from, 0.5)) * (1 - inOutCubic(prog(t, until - 0.1, 0.6)))
	dim(0.5 * up)
	let lines = txt.components(separatedBy: "\n")
	let size: CGFloat = V ? 110 : 104
	let lh = size * 1.1
	let top = CH / 2 - CGFloat(lines.count - 1) * lh / 2 + size * 0.35
	for (i, l) in lines.enumerated() {
		kinetic(l, x: CW / 2, baseline: top + CGFloat(i) * lh, size: size, weight: .semibold, color: C("text"), t: t,
			at: from + 0.15 + Double(i) * 0.2, exit: until - 0.2, stagger: 0.08, dur: 0.8, kern: -2)
	}
	return up
}
/// The step label over the take: a plain name for what the agent is doing ("Builds the set"), in the trailer's type,
/// with a strip of ticks counting the steps. Bottom-left in the landscape cut, top-left in the vertical.
func stepLabel(_ label: String, n: Int, total: Int, t: Double, at: Double, until: Double) {
	let a = outCubic(prog(t, at, 0.4)) * (1 - inCubic(prog(t, until - 0.3, 0.3)))
	if a <= 0 { return }
	save {
		setAlpha(a)
		scrim(top: V, depth: V ? 520 : 330, alpha: 0.55)
	}
	let x: CGFloat = V ? 64 : 96
	let tickY: CGFloat = V ? 150 : CH - 170
	let tw: CGFloat = V ? 70 : 52, th: CGFloat = V ? 8 : 6, gap: CGFloat = V ? 14 : 10
	save {
		setAlpha(a)
		for i in 0..<total {
			let r = CGRect(x: x + CGFloat(i) * (tw + gap), y: tickY, width: tw, height: th)
			fill(r, C("text", 0.22), radius: th / 2)
			let p: CGFloat = i < n - 1 ? 1 : (i == n - 1 ? outCubic(prog(t, at + 0.2, max(0.4, until - at - 0.5))) : 0)
			if p > 0 { fill(CGRect(x: r.minX, y: r.minY, width: r.width * p, height: th), C("accent"), radius: th / 2) }
		}
	}
	kinetic(label, x: x, baseline: tickY + (V ? 110 : 84), size: V ? 84 : 64, weight: .semibold, color: C("text"), t: t,
		at: at + 0.15, exit: until - 0.35, stagger: 0.07, align: 0, dur: 0.7, kern: -1)
}

/// The vanilla chat: lines over a translucent black band bottom-left, the edit line along the bottom with its `_`.
func mcChatLines(_ lines: [(String, Double)], _ t: Double, open: Bool, typed: String, caret: Bool, closeAt: Double) {
	let ck: CGFloat = V ? 2 : 1.5
	let chatW: CGFloat = V ? GW - 4 : 460
	let lineH: CGFloat = 9 * ck
	var rows: [(String, CGFloat)] = []
	for (str, at) in lines where t >= at {
		for piece in mcWrap(str, gx(chatW - 4), ck) { rows.append((piece, CGFloat(min(1, (t - at) / 0.12)))) }
	}
	let bottom: CGFloat = GH - (open ? 14 : 2) - (V ? 40 : 0)
	let shown = rows.suffix(V ? 12 : 14)
	for (i, row) in shown.enumerated() {
		let y = bottom - CGFloat(shown.count - i) * lineH
		mcPanel(CGRect(x: 0, y: gx(y), width: gx(chatW + 2), height: gx(lineH)), 0.5 * row.1)
		mcText(row.0, gx(2), gx(y + 1 + (ck - 1) * 0.5), k: ck, alpha: row.1)
	}
	if open {
		let barH: CGFloat = 12 * (V ? 1.6 : 1.3)
		let by = GH - 2 - barH - (V ? 40 : 0)
		mcPanel(CGRect(x: gx(2), y: gx(by), width: gx(GW - 4), height: gx(barH)), 0.5)
		let maxW = gx(GW - 12)
		var shownTyped = typed
		while mcWidth(shownTyped, ck) > maxW && !shownTyped.isEmpty { shownTyped.removeFirst() }
		let w = mcText(shownTyped, gx(4), gx(by + 2), k: ck)
		if caret { mcText("_", gx(4) + w + (typed.isEmpty ? 0 : G * ck), gx(by + 2), k: ck) }
	}
}
func sceneMCChat(_ o: Obj, _ t: Double) {
	fullFrame(pick(o, "bg"), t, since: d(o, "from"))
	let typeAt = d(o, "type_at"), sendAt = d(o, "send_at"), closeAt = d(o, "close_at")
	let prompt = s(o, "prompt")
	let n = t < typeAt ? 0 : min(prompt.count, Int((t - typeAt) * d(o, "cps", 40)))
	var lines: [(String, Double)] = [("§f<you> " + prompt, sendAt)]
	for l in arr(o, "lines") { lines.append((s(l, "mc"), d(l, "t"))) }
	let open = t < closeAt
	let caret = Int(t / 0.3) % 2 == 0
	mcChatLines(lines, t, open: open, typed: t < sendAt ? String(prompt.prefix(n)) : "", caret: caret, closeAt: closeAt)
}

/// A vanilla toast, sliding in from the right edge and back out: the system toast's own sprite, an item icon, a
/// yellow title and white lines. It grows to fit its text, as the game's system toasts do.
func mcToast(_ title: String, _ body: [String], icon: String, at: Double, until: Double, t: Double, sprite name: String = "toast/system", titleColor: String = "#FFFF00") {
	let inP = outCubic(prog(t, at, 0.6)), outP = inCubic(prog(t, until - 0.5, 0.5))
	let slide = inP * (1 - outP)
	if slide <= 0 { return }
	let k = TK
	let maxText = gx(GW - 4 - 30 * k - 8)
	var lines: [String] = []
	for b in body { lines += mcWrap(b, maxText, k) }
	let body = lines
	let titles = mcWrap(title, maxText, k)
	var textW: CGFloat = 0
	for b in titles + body { textW = max(textW, mcWidth(b, k)) }
	let wG = max(160, (textW / G) + 30 * k + 8)
	let hG = max(32, CGFloat(8 + 11 * (body.count + titles.count)) * k)
	let x = GW - wG * slide
	let r = CGRect(x: gx(x), y: gx(V ? 84 : 0), width: gx(wG), height: gx(hG))
	sprite(name, r)
	if let ic = png("item/\(icon).png") { blit(ic, CGRect(x: r.minX + gx(8 * k), y: r.minY + gx(8 * k), width: gx(16 * k), height: gx(16 * k))) }
	for (i, l) in titles.enumerated() {
		mcText(l, r.minX + gx(30 * k), r.minY + gx(CGFloat(7 + 11 * i) * k), k: k, color: titleColor, style: .flat)
	}
	for (i, b) in body.enumerated() {
		mcText(b, r.minX + gx(30 * k), r.minY + gx(CGFloat(7 + 11 * (titles.count + i)) * k), k: k, color: "#FFFFFF", style: .flat)
	}
}
/// A boss bar: the game's own background and progress sprites, its title above it in the game font.
func mcBossBar(_ title: String, _ p: CGFloat, color: String, y: CGFloat, alpha: CGFloat = 1) {
	let w: CGFloat = 182, x = (GW - w) / 2
	mcText(title, CW / 2, gx(y - 9 * TK - 1), k: TK, alpha: alpha, align: 0.5)
	if let bg = png("gui/sprites/boss_bar/\(color)_background.png") { blit(bg, CGRect(x: gx(x), y: gx(y), width: gx(w), height: gx(5)), alpha: alpha) }
	if p > 0, let fg = png("gui/sprites/boss_bar/\(color)_progress.png"),
		let part = fg.cropping(to: CGRect(x: 0, y: 0, width: max(1, Int(182 * p)), height: 5)) {
		blit(part, CGRect(x: gx(x), y: gx(y), width: gx(CGFloat(Int(182 * p))), height: gx(5)), alpha: alpha)
	}
}
/// A filled map held up: the map's own parchment, the camera's path and every actor in the map's ink, and the
/// player marker turned the way the camera looks (16 steps, as map markers turn).
func mcMap(_ track: Obj, _ k: Int, x: CGFloat, y: CGFloat, size: CGFloat) {
	guard let bg = png("map/map_background.png") else { return }
	let r = CGRect(x: gx(x), y: gx(y), width: gx(size), height: gx(size))
	blit(bg, r)
	let inner = r.insetBy(dx: gx(size * 7 / 64), dy: gx(size * 7 / 64))
	let b = (track["b"] as? [Double]) ?? [0, 0, 1, 1]
	let span = max(b[2] - b[0], b[3] - b[1])
	let cx = (b[0] + b[2]) / 2, cz = (b[1] + b[3]) / 2
	let cells: CGFloat = 64
	let cell = inner.width / cells
	func P(_ x: Double, _ z: Double) -> CGPoint {
		let u = CGFloat((x - cx) / span + 0.5) * cells, v = CGFloat((z - cz) / span + 0.5) * cells
		return CGPoint(x: inner.minX + floor(u) * cell, y: inner.minY + floor(v) * cell)
	}
	let ink = hex("#5A4527")
	let cam = (track["c"] as? [[Double]]) ?? []
	for (i, c) in cam.enumerated() where i <= k {
		let p = P(c[0], c[1])
		fill(CGRect(x: p.x, y: p.y, width: cell, height: cell), ink)
	}
	for a in (track["a"] as? [Obj]) ?? [] {
		let ps = (a["p"] as? [[Double]]) ?? []
		if ps.isEmpty { continue }
		let p = P(ps[min(k, ps.count - 1)][0], ps[min(k, ps.count - 1)][1])
		fill(CGRect(x: p.x - cell, y: p.y - cell, width: cell * 3, height: cell * 3), hex("#2B2015"))
		fill(CGRect(x: p.x, y: p.y, width: cell, height: cell), hex("#FFFFFF"))
	}
	if !cam.isEmpty, let marker = png("map/decorations/player.png") {
		let c = cam[min(k, cam.count - 1)]
		let p = P(c[0], c[1])
		let steps = (c[2] / 22.5).rounded() * 22.5
		save {
			ctx.interpolationQuality = .none
			ctx.translateBy(x: p.x + cell / 2, y: p.y + cell / 2)
			ctx.rotate(by: CGFloat(steps + 180) * .pi / 180)
			blit(marker, CGRect(x: -gx(4 * size / 64), y: -gx(4 * size / 64), width: gx(8 * size / 64), height: gx(8 * size / 64)))
		}
	}
}
func sceneMCMonitor(_ o: Obj, _ t: Double) {
	let clips = arr(o, "clips")
	guard let idx = clips.lastIndex(where: { t >= d($0, "at") }) else { return }
	let c = clips[idx]
	let at = d(c, "at"), dur = d(c, "dur")
	let step = Int(d(c, "step", 1))
	if s(c, "intro_from") == "t3", let app = ((J["scenes"] as? [Obj]) ?? []).first(where: { s($0, "type") == "t3" }) {
		// The match-cut: the take opens out of the app's line where the hidden game starts recording.
		let f = t3Focus(app, d(app, "cut_at"))
		let p = inOutCubic(prog(t, at, d(c, "intro", 0.8)))
		let start = CGRect(x: f.midX - 96, y: f.midY - 54, width: 192, height: 108)
		let r = lerpRect(start, CGRect(x: 0, y: 0, width: CW, height: CH), p)
		save {
			let radius = lerp(12, 0, p)
			ctx.addPath(CGPath(roundedRect: r, cornerWidth: radius, cornerHeight: radius, transform: nil))
			ctx.clip()
			ctx.translateBy(x: r.minX, y: r.minY)
			ctx.scaleBy(x: r.width / CW, y: r.height / CH)
			fullFrame(c, t, since: at, step: step)
		}
		if p < 1 { return }
	} else {
		fullFrame(c, t, since: at, step: step)
	}
	let track = pick(c, "track")
	let frames = (track["f"] as? [Int]) ?? []
	let k = max(0, min(frames.count - 1, Int(((t - at) * 30 * Double(step)).rounded(.down))))
	let fr = frames.isEmpty ? 0 : frames[k]
	let total = Int(d(track, "n"))
	let title = V ? String(format: "§cREC §f%04d§7/%04d", fr, total) : String(format: "§cREC §f%@ §7%04d/%04d", s(c, "shot"), fr, total)
	let ov = s(c, "overlay", "toast")
	if !s(c, "label").isEmpty {
		stepLabel(s(c, "label"), n: idx + 1, total: Int(d(o, "steps", Double(clips.count))), t: t, at: at, until: at + dur)
	}
	if ov.contains("rec") { mcBossBar(title, CGFloat(fr) / CGFloat(max(total, 1)), color: "red", y: V ? 112 : 12) }
	if ov.contains("toast") { mcToast(s(c, "toast_title"), (c["toast"] as? [String]) ?? [], icon: s(c, "icon", "writable_book"), at: at + 0.15, until: at + dur, t: t) }
	if s(c, "overlay").contains("map") && !(track["c"] as? [[Double]] ?? []).isEmpty {
		if V { mcMap(track, k, x: 6, y: 120, size: 96) } else { mcMap(track, k, x: 6, y: 12, size: 96) }
	}
}

/// The speaking shot, full frame, with the game's subtitle box bottom-right listing each word on its onset.
func sceneMCVoice(_ o: Obj, _ t: Double) {
	let from = d(o, "from")
	fullFrame(pick(o, "clip"), t, since: from)
	let ws = arr(o, "words")
	let shownWords = ws.filter { t >= from + d($0, "at") }
	let rows = shownWords.suffix(V ? 4 : 6).map { w -> String in String(format: "§7%5.2f s  §f%@", d(w, "at") - d(o, "offset"), s(w, "w")) }
	if rows.isEmpty { return }
	let k = TK
	let w = max(rows.map { mcWidth($0, k) }.max()!, mcWidth(s(o, V ? "box_title_v" : "box_title"), k)) / G + 8
	let lh: CGFloat = 10 * k
	let h = CGFloat(rows.count) * lh + 4 + lh
	let x = GW - w - 2, y: CGFloat = V ? 150 : 70
	mcPanel(CGRect(x: gx(x), y: gx(y), width: gx(w), height: gx(h)), 0.8)
	mcText(s(o, V ? "box_title_v" : "box_title"), gx(x + 4), gx(y + 2), k: k, color: "#FFFF55")
	for (i, r) in rows.enumerated() { mcText(r, gx(x + 4), gx(y + 2 + lh * CGFloat(i + 1)), k: k) }
}

/// The edit: the film scrubbing full frame, and its timeline over the top of the frame in the game's chrome.
func sceneMCEdit(_ o: Obj, _ t: Double) {
	let from = d(o, "from")
	let total = d(o, "seconds")
	let scrubAt = d(o, "scrub_at"), scrubDur = d(o, "scrub_dur")
	// The film plays at its own speed under the heading, then the playhead scrubs on from there.
	let play0 = CGFloat(scrubAt - from)
	let ph = t < scrubAt ? CGFloat(t - from) : play0 + inOutCubic(clamp(CGFloat((t - scrubAt) / scrubDur))) * (CGFloat(d(o, "scrub_to", total)) - play0)
	let step = Int(d(o, "step", 8))
	// The vertical cut is an editor: the film whole at the top, the timeline under it, the cut chip under that.
	let filmRect = CGRect(x: 0, y: 200, width: CW, height: CW * 9 / 16)
	let frameImg = t < scrubAt ? footage(s(o, "media"), inSec: 0, since: from, t: t)
		: footage(s(o, "media"), inSec: 0, since: 0, t: Double(ph) * 60 / Double(step) / FPS, step: step)
	if let img = frameImg {
		if V { image(img, filmRect) } else { placeFrame(img) }
	}
	let up = heading(o, t)
	let k = TK
	let px: CGFloat = 4, pw = GW - 8
	let laneH: CGFloat = V ? 14 : 9, gap: CGFloat = 3
	let names = ["video", "voice", "music", "sfx"]
	let labW: CGFloat = V ? 66 : 30
	let headH: CGFloat = 12 * k
	let ph0: CGFloat = V ? (filmRect.maxY + 48) / G : 4
	let panelH = headH + 6 + CGFloat(names.count) * (laneH + gap) + 10 * k
	let enter = outCubic(prog(t, d(o, "slide_at") - 0.35, 0.3)) * (1 - up)
	if enter <= 0 { return }
	ctx.saveGState(); let a0 = alphaNow; setAlpha(enter); defer { ctx.restoreGState(); alphaNow = a0 }
	mcPanel(CGRect(x: gx(px), y: gx(ph0), width: gx(pw), height: gx(panelH)), 0.72 * enter)
	mcText(s(o, V ? "title_v" : "title"), gx(px + 4), gx(ph0 + 3), k: k, alpha: enter)
	let laneX = px + 4 + labW, laneW = pw - 8 - labW
	func X(_ sec: Double) -> CGFloat { gx(laneX) + gx(laneW) * CGFloat(sec / total) }
	func laneY(_ i: Int) -> CGFloat { gx(ph0 + headH + 6 + CGFloat(i) * (laneH + gap)) }
	for (i, n) in names.enumerated() {
		mcText("§7" + n, gx(px + 4), laneY(i) + gx((laneH - 8 * k) / 2), k: k, alpha: enter)
		fill(CGRect(x: gx(laneX), y: laneY(i), width: gx(laneW), height: gx(laneH)), CGColor(gray: 0, alpha: 0.45 * enter))
	}
	// Video: each clip a block in a dye colour, landing on the beat one after another.
	let dyes = ["#F9FFFE", "#F9801D", "#C74EBD", "#3AB3DA", "#FED83D", "#80C71F", "#F38BAA", "#9D9D97", "#169C9C", "#8932B8", "#3C44AA", "#835432", "#5E7C16", "#B02E26"]
	let clips = (o["clips"] as? [[Any]]) ?? []
	let slideAt = d(o, "slide_at")
	for (i, cl) in clips.enumerated() {
		let st = (cl[0] as? Double) ?? 0, du = (cl[1] as? Double) ?? 0, kind = (cl[3] as? String) ?? "shot"
		if t < slideAt + Double(i) * 0.04 { continue }
		let x0 = snap(X(st)), x1 = snap(X(st + du))
		let r = CGRect(x: x0, y: laneY(0), width: max(G, x1 - x0 - G), height: gx(laneH))
		fill(r, kind == "black" ? hex("#000000") : hex(dyes[i % dyes.count]))
		fill(CGRect(x: r.minX, y: r.maxY - G, width: r.width, height: G), CGColor(gray: 0, alpha: 0.35))
	}
	let la = outCubic(prog(t, d(o, "lanes_at"), 0.2))
	if la > 0 {
		let voice = (o["voice"] as? [[Double]]) ?? []
		for v in voice {
			let x0 = snap(X(v[0])), x1 = snap(X(v[0] + v[1]))
			fill(CGRect(x: x0, y: laneY(1) + G, width: max(G, x1 - x0), height: gx(laneH - 2)), hex("#55FF55", la))
		}
		// The bed's level: full, and down by the duck under every line (a dip, not a pulse).
		let duck = d(o, "duck_db", -9)
		var x = gx(laneX)
		while x < gx(laneX + laneW) {
			let sec = Double((x - gx(laneX)) / gx(laneW)) * total
			let under = voice.contains { sec >= $0[0] - 0.03 && sec <= $0[0] + $0[1] + 0.2 }
			let hgt = under ? gx(laneH) * CGFloat(1 + duck / 14) * 0.5 : gx(laneH - 2)
			fill(CGRect(x: x, y: laneY(2) + gx(laneH) - G - hgt, width: G, height: hgt), hex("#FFAA00", la))
			x += G
		}
		for sec in (o["sfx"] as? [Double]) ?? [] { fill(CGRect(x: snap(X(sec)), y: laneY(3) + G, width: G, height: gx(laneH - 2)), hex("#FFFFFF", 0.8 * la)) }
	}
	// Cuts on words: marked in yellow as the playhead reaches them; the newest pops up as a large word chip.
	let reached = ((o["cuts"] as? [[Any]]) ?? []).filter { Double(ph) >= (($0[0] as? Double) ?? 0) }
	for (i, cut) in reached.enumerated() {
		let sec = (cut[0] as? Double) ?? 0, word = ((cut[1] as? String) ?? "").replacingOccurrences(of: "*", with: "")
		let x = snap(X(sec))
		fill(CGRect(x: x, y: laneY(0) - G, width: G, height: laneY(1) + gx(laneH) - laneY(0) + G), hex("#FFFF55"))
		if i == reached.count - 1 {
			let landed = editReach(o, sec)
			cutChip(word.trimmingCharacters(in: .punctuationCharacters), x: x, top: laneY(3) + gx(laneH + 10), t: t, at: landed)
		}
	}
	if V {
		// The editor's own line under the timeline, in the trailer's type.
		let lines = s(o, "note_v").components(separatedBy: "\n")
		for (i, l) in lines.enumerated() where !l.isEmpty {
			kinetic(l, x: CW / 2, baseline: 1640 + CGFloat(i) * 96, size: 80, weight: .semibold, color: C("text"), t: t,
				at: d(o, "slide_at") + 0.5 + Double(i) * 0.2, stagger: 0.07, dur: 0.8, kern: -1.5)
		}
	}
	if t >= scrubAt {
		let x = snap(X(Double(ph)))
		fill(CGRect(x: x, y: laneY(0) - gx(2), width: G, height: laneY(3) + gx(laneH + 2) - laneY(0)), hex("#FFFFFF"))
	}
}

/// When the edit's playhead reaches `sec` of the film (the same easing as the scene; bisection).
func editReach(_ o: Obj, _ sec: Double) -> Double {
	let from = d(o, "from"), scrubAt = d(o, "scrub_at"), scrubDur = d(o, "scrub_dur"), to = d(o, "scrub_to", d(o, "seconds"))
	let p0 = scrubAt - from
	if sec <= p0 { return from + sec }
	var lo = 0.0, hi = 1.0
	for _ in 0..<40 {
		let mid = (lo + hi) / 2
		let u = Double(inOutCubic(CGFloat(mid)))
		if p0 + u * (to - p0) < sec { lo = mid } else { hi = mid }
	}
	return scrubAt + scrubDur * lo
}
/// The cut-on-word chip: a light pill naming the word the cut lands on, popping up (a settle) when the playhead
/// reaches the cut, a hairline from the playhead down to it.
func cutChip(_ word: String, x: CGFloat, top: CGFloat, t: Double, at: Double) {
	let p = settle(prog(t, at, 0.45))
	if p <= 0 { return }
	let size: CGFloat = V ? 72 : 50
	let fLead = font(size, .regular), fWord = font(size, .bold)
	let lead = "Cut on ", w = "\u{201C}" + word + "\u{201D}"
	let tw = width(lead, fLead) + width(w, fWord)
	let padX = size * 0.6, h = size * 1.7
	let cx = clamp(x, tw / 2 + padX + 40, CW - tw / 2 - padX - 40)
	let y = top + (V ? 120 : 60)
	save {
		setAlpha(clamp(p * 2))
		fill(CGRect(x: x - 1.5, y: top, width: 3, height: y - top), C("text", 0.7))
		ctx.translateBy(x: cx, y: y + h / 2)
		ctx.scaleBy(x: lerp(0.6, 1, p), y: lerp(0.6, 1, p))
		ctx.translateBy(x: -cx, y: -(y + h / 2))
		let r = CGRect(x: cx - tw / 2 - padX, y: y, width: tw + 2 * padX, height: h)
		shadow(r, radius: h / 2, alpha: 0.5, blur: 30, dy: 10)
		fill(r, C("text"), radius: h / 2)
		let base = y + h / 2 + size * 0.36
		let lw = text(lead, r.minX + padX, base, fLead, C("bg"))
		text(w, r.minX + padX + lw, base, fWord, hex("#2f7a1f"))
	}
}

/// The review: the reviewed film under the heading, then a side panel with the criteria the last review round scored
/// up (before → after, bars growing from the old score to the new), what changed between the two takes, and the
/// average against the pass line it has not reached.
func sceneMCScores(_ o: Obj, _ t: Double) {
	let from = d(o, "from")
	fullFrame(pick(o, "clip"), t, since: from, speed: d(pick(o, "clip"), "speed", 1))
	heading(o, t)
	let at = d(o, "panel_at")
	let pin = outCubic(prog(t, at, 0.6))
	if pin <= 0 { return }
	let cl = pick(o, "climb")
	let rows = (cl["improved"] as? [[Any]]) ?? []
	let changed = (cl["changed"] as? [String]) ?? []
	let avg = (cl["average"] as? [Double]) ?? [0, 0]
	let fs: CGFloat = V ? 64 : 30          // body size (vertical: capitals at least 44 px)
	let fK = font(V ? 60 : 20, .medium, .mono), fB = font(fs, .regular), fV = font(fs, .medium, .mono), fT = font(V ? 64 : 40, .semibold)
	let pw: CGFloat = V ? CW - 96 : 700
	let rowH: CGFloat = V ? 150 : 74
	let headH: CGFloat = V ? 0 : 110
	let fC = V ? font(fs, .regular) : font(27, .regular)
	let pwFor: CGFloat = (V ? CW - 96 : 700) - (V ? 88 : 80)
	let changedLines = changed.flatMap { c in wrapText(c, fC, pwFor - 40).enumerated().map { ($0.offset == 0 ? "·  " : "    ") + $0.element } }
	let changedH: CGFloat = (V ? 86 : 42) * CGFloat(changedLines.count) + (V ? 90 : 50)
	let footH: CGFloat = V ? 180 : 70
	let ph = 56 + headH + CGFloat(rows.count) * rowH + changedH + footH
	let px: CGFloat = V ? 48 : CW - pw - 80
	let py: CGFloat = V ? CH - ph - 70 : 70
	let r = CGRect(x: px + (1 - pin) * (V ? 0 : 60), y: py + (1 - pin) * (V ? 60 : 0), width: pw, height: ph)
	save {
		setAlpha(pin)
		shadow(r, radius: 22, alpha: 0.45, blur: 50, dy: 18)
		fill(r, CGColor(srgbRed: 0.07, green: 0.067, blue: 0.06, alpha: 0.86), radius: 22)
		stroke(r, C("text", 0.12), radius: 22, width: 1.5)
	}
	let x0 = r.minX + (V ? 44 : 40), x1 = r.maxX - (V ? 44 : 40)
	var y = r.minY + 40
	save {
		setAlpha(pin)
		if !V {
			text(String(format: "REVIEW ROUND %d → %d", Int(d(cl, "from_round")), Int(d(cl, "to_round"))), x0, y + 20, fK, C("accent"), kern: 1)
			text("Scored up by fresh reviewers", x0, y + 72, fT, C("text"), kern: -0.5)
			y += headH
		}
		for (i, row) in rows.enumerated() {
			let name = (row[0] as? String) ?? "", a = (row[1] as? Double) ?? 0, b = (row[2] as? Double) ?? 0
			let rt = at + 0.4 + Double(i) * 0.35
			let ra = outCubic(prog(t, rt, 0.4))
			let grow = inOutCubic(prog(t, rt + 0.3, 0.8))
			let v = a + (b - a) * Double(grow)
			save {
				setAlpha(ra)
				let base = y + fs * 0.95
				text(name.prefix(1).uppercased() + name.dropFirst(), x0, base, fB, C("text"))
				let after = String(format: "%.1f", v)
				let wA = width(after, fV)
				text(after, x1, base, fV, grow >= 1 ? C("accent") : C("text"), align: 1)
				text(String(format: "%.1f  →  ", a), x1 - wA, base, fV, C("muted"), align: 1)
				let by = base + (V ? 34 : 18), bh: CGFloat = V ? 14 : 8
				let bw = x1 - x0
				fill(CGRect(x: x0, y: by, width: bw, height: bh), C("text", 0.12), radius: bh / 2)
				fill(CGRect(x: x0, y: by, width: bw * CGFloat(a / 10), height: bh), C("muted", 0.8), radius: bh / 2)
				let gx0 = x0 + bw * CGFloat(a / 10)
				fill(CGRect(x: gx0 - bh / 2, y: by, width: bw * CGFloat((v - a) / 10) + bh / 2, height: bh), C("accent"), radius: bh / 2)
			}
			y += rowH
		}
		let ca = outCubic(prog(t, at + 0.4 + Double(rows.count) * 0.35 + 0.5, 0.5))
		save {
			setAlpha(ca)
			fill(CGRect(x: x0, y: y + 4, width: x1 - x0, height: 1.2), C("text", 0.12))
			y += V ? 80 : 40
			text(V ? "What changed:" : "WHAT CHANGED", x0, y, V ? fB : fK, V ? C("muted") : C("muted"), kern: V ? 0 : 1)
			for c in changedLines {
				y += V ? 86 : 42
				text(c, x0, y, fC, C("text"))
			}
		}
		y += V ? 100 : 56
		let fa = outCubic(prog(t, at + 0.4 + Double(rows.count) * 0.35 + 1.2, 0.5))
		let line1 = String(format: "Average %.2f → %.2f", avg[0], avg[1])
		let line2 = String(format: "Pass line %.1f: not there yet", d(cl, "pass_line", 7))
		if V {
			text(line1, x0, y, fB, C("muted"), alpha: fa)
			text(line2, x0, y + 86, fB, C("muted"), alpha: fa)
		} else {
			text(line1 + "  ·  " + line2, x0, y, font(22, .regular), C("muted"), alpha: fa)
		}
	}
}

/// The end: the dusk shot full frame, the name in the game's font with its shadow, the command in the chat's edit
/// line, the repository in grey.
func sceneMCEnd(_ o: Obj, _ t: Double) {
	let from = d(o, "from"), to = d(o, "to")
	fullFrame(pick(o, "clip"), t, since: from)
	let fade = 1 - inOutCubic(prog(t, to - 0.6, 0.6))
	save {
		setAlpha(fade)
		fill(CGRect(x: 0, y: 0, width: CW, height: CH), CGColor(gray: 0, alpha: 0.25))
		let titleK: CGFloat = V ? 4 : 6
		let ty: CGFloat = V ? 150 : 70
		mcText(s(o, "name"), CW / 2, gx(ty), k: titleK, style: .outline, alpha: outCubic(prog(t, from + 0.1, 0.2)), align: 0.5)
		let lines = s(o, V ? "tagline_v" : "tagline").components(separatedBy: "\n")
		for (i, l) in lines.enumerated() {
			mcText(l, CW / 2, gx(ty + 9 * titleK + 8 + CGFloat(i) * 11 * TK), k: TK, alpha: outCubic(prog(t, from + 0.35, 0.2)), align: 0.5)
		}
		let cmd = s(o, "command")
		let ck: CGFloat = V ? 1.5 : 1
		let n = min(cmd.count, max(0, Int((t - from - 0.6) * 40)))
		let by = ty + 9 * titleK + 14 + CGFloat(lines.count) * 11 * TK
		let bw = mcWidth(cmd, ck) / G + 12
		mcPanel(CGRect(x: CW / 2 - gx(bw / 2), y: gx(by), width: gx(bw), height: gx(12 * ck)), 0.55)
		let w = mcText(String(cmd.prefix(n)), CW / 2 - gx(bw / 2) + gx(4), gx(by + 2 * ck), k: ck)
		if Int(t / 0.3) % 2 == 0 { mcText("_", CW / 2 - gx(bw / 2) + gx(4) + w + G * ck, gx(by + 2 * ck), k: ck) }
		for (i, u) in s(o, V ? "url_v" : "url").components(separatedBy: "\n").enumerated() {
			mcText("§7" + u, CW / 2, gx(by + 12 * ck + 6 + CGFloat(i) * 11 * TK), k: TK, alpha: outCubic(prog(t, from + 1.6, 0.2)), align: 0.5)
		}
		let dis = s(o, V ? "disclaimer_v" : "disclaimer").components(separatedBy: "\n")
		for (i, l) in dis.enumerated() {
			mcText("§8" + l, CW / 2, CH - gx(CGFloat(dis.count - i) * 14 + (V ? 60 : 8)), k: V ? 1.5 : 1, alpha: outCubic(prog(t, from + 1.8, 0.2)), align: 0.5)
		}
	}
}
/// The payoff: takes cut together hard, full frame, nothing over them but the game's own captions.
func sceneMCReel(_ o: Obj, _ t: Double) {
	let clips = arr(o, "clips")
	guard let c = clips.last(where: { t >= d($0, "at") }) else { return }
	fullFrame(c, t, since: d(c, "at"))
}
/// The finished film: full frame, nothing over it.
func sceneMCFilm(_ o: Obj, _ t: Double) { fullFrame(pick(o, "clip"), t, since: d(o, "from")) }

// MARK: - the agent app (a rebuild of the T3 Code window: sidebar, thread, composer; drawn, never captured)

let T3 = (bg: "#0B0B0D", side: "#101013", line: "#232328", card: "#16161A", text: "#ECECEE", muted: "#8B8B93", dim: "#55555C",
	blue: "#3B82F6", user: "#1D1D22", code: "#0F0F12", green: "#4ADE80")
func t3c(_ k: String, _ a: CGFloat = 1) -> CGColor { hex(k, a) }

/// The window's frame on the canvas (the vertical cut is the thread column alone, edge to edge, type 1.6x larger).
func t3Window() -> CGRect { V ? CGRect(x: 16, y: 120, width: 1048, height: 1700) : CGRect(x: 150, y: 80, width: 1620, height: 920) }

struct T3Row { let kind: String; let text: String; let at: Double; let h: CGFloat; let extra: String }
// Sizes: in the vertical cut every capital is at least 44 px (SF's cap height is about 0.7 of the size).
let t3Sans = font(V ? 64 : 30, .regular), t3Mono = font(V ? 60 : 21, .regular, .mono), t3Tool = font(V ? 64 : 21, .regular)
func t3Rows(_ o: Obj, _ col: CGRect) -> [T3Row] {
	var rows: [T3Row] = []
	let sent = d(o, "send_at")
	for l in wrapText(s(o, "prompt"), t3Sans, col.width * (V ? 0.94 : 0.62)) { rows.append(T3Row(kind: "user", text: l, at: sent, h: CTFontGetSize(t3Sans) * 1.45, extra: "")) }
	rows.append(T3Row(kind: "gap", text: "", at: sent, h: V ? 40 : 34, extra: ""))
	for m in arr(o, "messages") {
		let at = d(m, "t")
		if s(m, "kind") == "text" {
			// Streams at reading speed: each line starts when the words before it have arrived.
			var t0 = at
			for l in wrapText(s(m, "text"), t3Sans, col.width - 20) {
				rows.append(T3Row(kind: "agent", text: l, at: t0, h: CTFontGetSize(t3Sans) * 1.45, extra: String(d(m, "wps", 6))))
				t0 += Double(l.split(separator: " ").count) / d(m, "wps", 6)
			}
			rows.append(T3Row(kind: "gap", text: "", at: at, h: V ? 26 : 18, extra: ""))
		} else {
			// A tool call the way the app draws one: small, normal weight, the command muted beside "Ran".
			let cols = Int((col.width - (V ? 24 : 70)) / width("M", t3Mono))
			if V {
				rows.append(T3Row(kind: "tool", text: s(m, "title"), at: at, h: CTFontGetSize(t3Tool) * 1.45, extra: ""))
				// The vertical column fits about 26 mono characters: wrapped lines start flush (no hanging indent).
				for p in wrap(s(m, "command"), cols) {
					rows.append(T3Row(kind: "cmd", text: p.trimmingCharacters(in: .whitespaces), at: at, h: CTFontGetSize(t3Mono) * 1.3, extra: ""))
				}
			} else {
				rows.append(T3Row(kind: "tool", text: s(m, "title"), at: at, h: CTFontGetSize(t3Tool) * 2.1, extra: s(m, "command")))
			}
			for l in arr(m, "lines") {
				for (j, p) in wrap(s(l, "text"), cols).enumerated() {
					rows.append(T3Row(kind: "out", text: V ? p.trimmingCharacters(in: .whitespaces) : (j > 0 ? "  " + p : p), at: d(l, "t"), h: CTFontGetSize(t3Mono) * (V ? 1.3 : 1.7), extra: ""))
				}
			}
			rows.append(T3Row(kind: "toolend", text: "", at: at, h: V ? 26 : 14, extra: ""))
		}
	}
	return rows
}
/// The thread's column inside the window.
func t3Column() -> CGRect {
	let w = t3Window()
	if V { return CGRect(x: w.minX + 30, y: w.minY + 160, width: w.width - 60, height: w.height - 160 - 250) }
	let sideW: CGFloat = 300
	return CGRect(x: w.minX + sideW + 90, y: w.minY + 90, width: w.width - sideW - 180, height: w.height - 90 - 190)
}
func t3Layout(_ rows: [T3Row], _ t: Double, _ col: CGRect) -> [CGFloat] {
	var ys: [CGFloat] = []
	let hs = rows.map { $0.h * inOutCubic(prog(t, $0.at, 0.35)) }
	let total = hs.reduce(0, +)
	var y = total <= col.height - 80 ? col.minY : col.maxY - 80 - total
	for h in hs { ys.append(y); y += h }
	return ys
}
/// The slow push-in while the agent works (about 8 %), toward the upper part of the thread where the work is.
func t3Push(_ o: Obj, _ t: Double) -> (CGFloat, CGPoint) {
	let col = t3Column()
	let k = 1 + (V ? 0.025 : 0.14) * inOutCubic(prog(t, d(o, "send_at"), d(o, "cut_at") - d(o, "send_at")))
	return (k, CGPoint(x: col.midX, y: col.minY + col.height * (V ? 0.2 : 0.15)))
}
/// The row the match-cut dives into, in layout coordinates.
func t3FocusRaw(_ o: Obj, _ t: Double) -> CGRect {
	let col = t3Column()
	let rows = t3Rows(o, col)
	let ys = t3Layout(rows, t, col)
	let i = rows.lastIndex { $0.kind == "out" && $0.text.contains(s(o, "focus")) } ?? rows.count - 1
	return CGRect(x: col.minX + 24, y: ys[i], width: col.width - 48, height: rows[i].h)
}
/// The same row on screen (after the push-in).
func t3Focus(_ o: Obj, _ t: Double) -> CGRect {
	let f = t3FocusRaw(o, t)
	let (k, p) = t3Push(o, t)
	return CGRect(x: p.x + (f.minX - p.x) * k, y: p.y + (f.minY - p.y) * k, width: f.width * k, height: f.height * k)
}
func sceneT3(_ o: Obj, _ t: Double) {
	let from = d(o, "from"), cutAt = d(o, "cut_at"), sendAt = d(o, "send_at")
	let win = t3Window()
	let col = t3Column()
	let enter = inOutCubic(prog(t, from + 0.2, 1.0))
	let z = inOutCubic(prog(t, cutAt, 0.9))
	let focus = t3FocusRaw(o, min(t, cutAt))
	let (pk, pp) = t3Push(o, min(t, cutAt))
	save {
		// Eases in from slightly smaller; pushes in slowly while the agent works; at the cut it dives into the line
		// where the game starts recording.
		let s0 = lerp(0.94, 1, enter)
		ctx.translateBy(x: win.midX, y: win.midY)
		ctx.scaleBy(x: s0, y: s0)
		ctx.translateBy(x: -win.midX, y: -win.midY)
		// While the prompt is typed the camera sits on the composer (larger, nearer the middle of the frame), then
		// eases back out to the thread as it is sent.
		let zt = inOutCubic(prog(t, d(o, "type_from") - 1.1, 1.0)) * (1 - inOutCubic(prog(t, sendAt + 0.1, 0.9)))
		if zt > 0 {
			let ca = V ? CGPoint(x: col.midX, y: win.maxY - 210) : CGPoint(x: col.midX, y: win.maxY - 91)
			let kz: CGFloat = 1 + (V ? 0.04 : 0.3) * zt
			ctx.translateBy(x: ca.x, y: ca.y - (V ? 560 : 330) * zt)
			ctx.scaleBy(x: kz, y: kz)
			ctx.translateBy(x: -ca.x, y: -ca.y)
		}
		ctx.translateBy(x: pp.x, y: pp.y)
		ctx.scaleBy(x: pk, y: pk)
		ctx.translateBy(x: -pp.x, y: -pp.y)
		let k = 1 + z * 5
		ctx.translateBy(x: focus.midX, y: focus.midY)
		ctx.scaleBy(x: k, y: k)
		ctx.translateBy(x: -focus.midX, y: -focus.midY)
		setAlpha(enter * (1 - inOutCubic(prog(t, cutAt + 0.45, 0.45))))
		shadow(win, radius: 16, alpha: 0.6, blur: 60, dy: 24)
		fill(win, t3c(T3.bg), radius: 16)
		stroke(win, t3c(T3.line), radius: 16, width: 1.5)
		// Title bar: the window's three controls and the thread's title.
		for i in 0..<3 {
			ctx.setFillColor(t3c(["#FF5F57", "#FEBC2E", "#28C840"][i]))
			ctx.fillEllipse(in: CGRect(x: win.minX + 22 + CGFloat(i) * 22, y: win.minY + 20, width: 13, height: 13))
		}
		let sideW: CGFloat = V ? 0 : 300
		let headerH: CGFloat = V ? 130 : 50
		if !V {
			// The sidebar: projects and their threads.
			fill(CGRect(x: win.minX + 1, y: win.minY + 50, width: sideW, height: win.height - 51), t3c(T3.side))
			fill(CGRect(x: win.minX + sideW, y: win.minY + 50, width: 1.2, height: win.height - 51), t3c(T3.line))
			let nf = font(17, .medium)
			let nb = CGRect(x: win.minX + 18, y: win.minY + 66, width: sideW - 36, height: 40)
			stroke(nb, t3c(T3.line), radius: 9, width: 1.2)
			text("+  New thread", nb.minX + 16, nb.midY + 6, nf, t3c(T3.text))
			var y = win.minY + 140
			text("PROJECTS", win.minX + 22, y, font(12, .semibold), t3c(T3.dim), kern: 0.8)
			y += 28
			for p in arr(o, "projects") {
				text("▾  " + s(p, "name"), win.minX + 22, y + 14, font(17, .semibold), t3c(T3.text))
				y += 34
				for th in (p["threads"] as? [String]) ?? [] {
					let active = th == s(o, "thread")
					if active { fill(CGRect(x: win.minX + 12, y: y - 4, width: sideW - 24, height: 32), t3c("#1C1C21"), radius: 8) }
					text(th, win.minX + 46, y + 17, font(16, .regular), active ? t3c(T3.text) : t3c(T3.muted))
					if active {
						let pulse = (t > sendAt && t < cutAt) ? 0.55 + 0.45 * sin(t * 5) : 0
						ctx.setFillColor(t3c(T3.blue, CGFloat(pulse)))
						ctx.fillEllipse(in: CGRect(x: win.minX + sideW - 34, y: y + 8, width: 8, height: 8))
					}
					y += 34
				}
				y += 10
			}
			text(s(o, "thread"), win.minX + sideW + 30, win.minY + 33, font(18, .semibold), t3c(T3.text))
			text(s(o, "project_path"), win.minX + sideW + 30 + width(s(o, "thread"), font(18, .semibold)) + 14, win.minY + 33, font(15, .regular, .mono), t3c(T3.dim))
		} else {
			text(s(o, "thread"), win.minX + 46, win.minY + 106, font(64, .semibold), t3c(T3.text))
		}
		fill(CGRect(x: win.minX + sideW + 1, y: win.minY + headerH, width: win.width - sideW - 2, height: 1.2), t3c(T3.line))
		// The thread.
		let rows = t3Rows(o, col)
		let ys = t3Layout(rows, t, col)
		save {
			ctx.clip(to: CGRect(x: col.minX - 20, y: win.minY + headerH + 2, width: col.width + 40, height: col.maxY - win.minY - headerH))
			var toolTop: Int? = nil
			for (i, r) in rows.enumerated() {
				if r.kind == "tool" && t >= r.at { toolTop = i }
				if r.kind == "toolend", let tp = toolTop {
					let lastVisible = rows.indices.filter { $0 > tp && $0 <= i && t >= rows[$0].at && rows[$0].kind != "toolend" }.last ?? tp
					let bottom = ys[lastVisible] + rows[lastVisible].h + (V ? 14 : 6)
					let box = CGRect(x: col.minX, y: ys[tp], width: col.width, height: bottom - ys[tp])
					fill(box, t3c(T3.code), radius: 10)
					stroke(box, t3c(T3.line), radius: 10, width: 1.2)
					toolTop = nil
				}
			}
			let userRows = rows.filter { $0.kind == "user" }
			let uw = (userRows.map { width($0.text, t3Sans) }.max() ?? 0) + 44
			var lastY = col.minY
			for (i, r) in rows.enumerated() where t >= r.at {
				let y = ys[i]
				lastY = max(lastY, y + r.h)
				let a = inOutCubic(prog(t, r.at, 0.3))
				let ind: CGFloat = V ? 12 : 42
				switch r.kind {
				case "user":
					if i == rows.firstIndex(where: { $0.kind == "user" }) {
						let bub = CGRect(x: col.maxX - uw, y: y - 6 + (1 - a) * 20, width: uw, height: CGFloat(userRows.count) * r.h + 16)
						fill(bub, t3c(T3.user, a), radius: 18)
					}
					text(r.text, col.maxX - uw + 22, y + r.h * 0.72 + (1 - a) * 20, t3Sans, t3c(T3.text), alpha: a)
				case "agent":
					let ws = r.text.split(separator: " ")
					let n = min(ws.count, Int((t - r.at) * (Double(r.extra) ?? 6)) + 1)
					text(ws.prefix(n).joined(separator: " "), col.minX, y + r.h * 0.72, t3Sans, t3c(T3.text))
				case "tool":
					let next = rows.first { $0.kind == "out" && $0.at > r.at }?.at ?? r.at
					let running = t < next
					let cy = y + r.h * 0.5
					if running {
						spinner(CGPoint(x: col.minX + ind / 2 + 2, y: cy), V ? 18 : 7, t, t3c(T3.muted))
					} else {
						text("✓", col.minX + (V ? 10 : 14), cy + CTFontGetSize(t3Tool) * 0.35, t3Tool, t3c(T3.green), alpha: a)
					}
					let tw = text(r.text, col.minX + ind + (V ? 62 : 4), cy + CTFontGetSize(t3Tool) * 0.35, t3Tool, t3c(T3.muted), alpha: a)
					if !r.extra.isEmpty {
						text(r.extra, col.minX + ind + 4 + tw + 10, cy + CTFontGetSize(t3Tool) * 0.35, t3Mono, t3c(T3.muted), alpha: a)
					}
					text("›", col.maxX - (V ? 50 : 30), cy + CTFontGetSize(t3Tool) * 0.35, t3Tool, t3c(T3.dim), alpha: a)
				case "cmd":
					text(r.text, col.minX + ind, y + r.h * 0.72, t3Mono, t3c(T3.muted), alpha: a)
				case "out":
					text(r.text, col.minX + ind + (V ? 0 : 4), y + r.h * 0.72, t3Mono, t3c("#B4B4BC"), alpha: a)
				default: break
				}
			}
			// The live status line: a spinner, "Working…" and the time since the prompt was sent.
			let wa = outCubic(prog(t, sendAt + 0.3, 0.3))
			if wa > 0 {
				let sec = max(0, Int(t - sendAt))
				let wy = lastY + (V ? 30 : 22)
				let wf = V ? font(60, .regular) : font(22, .regular)
				spinner(CGPoint(x: col.minX + (V ? 18 : 10), y: wy + CTFontGetSize(wf) * 0.5), V ? 16 : 8, t, t3c(T3.muted), alpha: wa)
				let ww = text(s(o, "working", "Working…"), col.minX + (V ? 50 : 30), wy + CTFontGetSize(wf) * 0.85, wf, t3c(T3.muted), alpha: wa)
				text(String(format: "%d:%02d", sec / 60, sec % 60), col.minX + (V ? 50 : 30) + ww + (V ? 22 : 12), wy + CTFontGetSize(wf) * 0.85,
					V ? font(60, .regular, .mono) : font(22, .regular, .mono), t3c(T3.dim), alpha: wa)
			}
		}
		// The composer: the prompt typed at a human pace, one think-pause before Enter.
		let cbH = V ? lerp(340, 190, inOutCubic(prog(t, sendAt, 0.5))) : 118
		let cb = V ? CGRect(x: col.minX - 14, y: win.maxY - cbH - 40, width: col.width + 28, height: cbH)
			: CGRect(x: col.minX - 20, y: win.maxY - 150, width: col.width + 40, height: 118)
		fill(cb, t3c(T3.card), radius: 18)
		stroke(cb, t < sendAt && t > d(o, "type_from") - 0.5 ? t3c(T3.dim) : t3c(T3.line), radius: 18, width: 1.5)
		let keys = (o["keys"] as? [Double]) ?? []
		let n = keys.filter { t >= $0 }.count
		let prompt = s(o, "prompt")
		let pf = t3Sans
		let typed = t < sendAt ? String(prompt.prefix(n)) : ""
		let tx = cb.minX + 24, ty = cb.minY + (V ? min(84, cbH * 0.45) : 42)
		let maxLines = V ? 3 : 2
		if typed.isEmpty { text(V ? "Ask anything" : s(o, "placeholder"), tx, ty, pf, t3c(T3.dim)) }
		let plines = wrapText(typed, pf, cb.width - (V ? 110 : 48))
		for (i, l) in plines.suffix(maxLines).enumerated() { text(l, tx, ty + CGFloat(i) * CTFontGetSize(pf) * 1.3, pf, t3c(T3.text)) }
		if t < sendAt && (Int(t * 2) % 2 == 0 || (n > 0 && n < prompt.count)) {
			let last = plines.suffix(maxLines).last ?? ""
			let cy = ty + CGFloat(max(0, min(plines.count, maxLines) - 1)) * CTFontGetSize(pf) * 1.3
			fill(CGRect(x: tx + width(last, pf) + 2, y: cy - CTFontGetSize(pf) * 0.8, width: V ? 4 : 2, height: CTFontGetSize(pf)), t3c(T3.text))
		}
		if !V { text(s(o, "composer_hint"), tx, cb.maxY - 22, font(15, .regular), t3c(T3.dim)) }
		let bs: CGFloat = V ? 64 : 38
		let sb = CGRect(x: cb.maxX - bs - 20, y: cb.maxY - bs - 16, width: bs, height: bs)
		let ready = !typed.isEmpty
		ctx.setFillColor(ready ? t3c(T3.text) : t3c(T3.line))
		ctx.fillEllipse(in: sb)
		ctx.setStrokeColor(t3c(T3.bg))
		ctx.setLineWidth(V ? 5 : 3)
		ctx.setLineCap(.round)
		let u = bs / 38
		ctx.move(to: CGPoint(x: sb.midX, y: sb.midY + 9 * u)); ctx.addLine(to: CGPoint(x: sb.midX, y: sb.midY - 9 * u))
		ctx.move(to: CGPoint(x: sb.midX - 7 * u, y: sb.midY - 2 * u)); ctx.addLine(to: CGPoint(x: sb.midX, y: sb.midY - 9 * u))
		ctx.addLine(to: CGPoint(x: sb.midX + 7 * u, y: sb.midY - 2 * u))
		ctx.strokePath()
	}
}
/// A small activity spinner: three quarters of a ring, turning once a second.
func spinner(_ c: CGPoint, _ r: CGFloat, _ t: Double, _ color: CGColor, alpha: CGFloat = 1) {
	save {
		setAlpha(alpha)
		ctx.setStrokeColor(color)
		ctx.setLineWidth(max(2, r * 0.28))
		ctx.setLineCap(.round)
		let a0 = CGFloat(t * 2 * .pi)
		ctx.addArc(center: c, radius: r, startAngle: a0, endAngle: a0 + .pi * 1.5, clockwise: false)
		ctx.strokePath()
	}
}

/// A beat on the calm canvas: one line or two, large, easing in and holding, then easing out.
func sceneCard(_ o: Obj, _ t: Double) {
	let from = d(o, "from"), to = d(o, "to")
	if o["bg"] != nil {
		// Over footage, never an empty canvas: the picture eases up from black under the type.
		fullFrame(pick(o, "bg"), t, since: from)
		dim(CGFloat(d(o, "dim", 0.5)) + 0.5 * (1 - outCubic(prog(t, from, 1.2))))
	}
	let lines = s(o, V ? "text_v" : "text", s(o, "text")).components(separatedBy: "\n")
	let size: CGFloat = CGFloat(d(o, "size", V ? 112 : 104))
	let lh = size * 1.12
	let top = CH / 2 - CGFloat(lines.count - 1) * lh / 2 + size * 0.35
	let k = s(o, "kicker")
	if !k.isEmpty {
		kinetic(k, x: CW / 2, baseline: top - lh * 0.9, size: V ? 34 : 30, weight: .medium, color: C("accent"), t: t, at: from + 0.1,
			exit: to - 0.55, stagger: 0, dur: 0.8, face: .mono, kern: 0)
	}
	for (i, l) in lines.enumerated() {
		kinetic(l, x: CW / 2, baseline: top + CGFloat(i) * lh, size: size, weight: .semibold, color: C("text"), t: t,
			at: from + 0.2 + Double(i) * 0.25, exit: to - 0.55, stagger: 0.08, dur: 0.9, kern: -2)
	}
}

/// Footage enters from a frame on the canvas and leaves the same way (ease-in-out), so the wrapper holds it.
func framed(_ o: Obj, _ t: Double, _ draw: () -> Void) {
	let from = d(o, "from"), to = d(o, "to")
	let pin = inOutCubic(prog(t, from, d(o, "ease_in", 0)))
	let pout = inOutCubic(prog(t, to - d(o, "ease_out", 0), d(o, "ease_out", 0)))
	let p = d(o, "ease_in", 0) > 0 ? pin : 1
	let q = d(o, "ease_out", 0) > 0 ? pout : 0
	let s0 = lerp(0.72, 1, p) * lerp(1, 0.72, q)
	if s0 >= 0.999 { draw(); return }
	let r = CGRect(x: CW * (1 - s0) / 2, y: CH * (1 - s0) / 2, width: CW * s0, height: CH * s0)
	let radius = 24 * (1 - (s0 - 0.72) / 0.28)
	save {
		setAlpha(min(1, (1 - q) * 1.4) * min(1, p * 1.6 + (d(o, "ease_in", 0) > 0 ? 0 : 1)))
		shadow(r, radius: radius, alpha: 0.5)
		ctx.addPath(CGPath(roundedRect: r, cornerWidth: radius, cornerHeight: radius, transform: nil))
		ctx.clip()
		ctx.translateBy(x: r.minX, y: r.minY)
		ctx.scaleBy(x: s0, y: s0)
		draw()
	}
}

/// The end: the barn at sunset under a dark veil, the name, one line, the command, the repository; the whole lockup
/// held for seconds, then a fade.
func sceneEndModern(_ o: Obj, _ t: Double) {
	let from = d(o, "from"), to = d(o, "to")
	let fade = 1 - inOutCubic(prog(t, to - 0.8, 0.8))
	save {
		setAlpha(fade)
		if o["bg"] != nil {
			fullFrame(pick(o, "bg"), t, since: from)
			dim(CGFloat(d(o, "dim", 0.6)))
		}
		let y0: CGFloat = V ? 640 : 360
		kinetic(s(o, "name"), x: CW / 2, baseline: y0, size: V ? 170 : 150, weight: .semibold, color: C("text"), t: t, at: from + 0.3,
			stagger: 0, dur: 1.0, kern: -4)
		let tl = s(o, V ? "tagline_v" : "tagline", s(o, "tagline")).components(separatedBy: "\n")
		for (i, l) in tl.enumerated() {
			kinetic(l, x: CW / 2, baseline: y0 + (V ? 130 : 105) + CGFloat(i) * (V ? 86 : 70), size: V ? 66 : 56, weight: .medium, color: C("text"), t: t,
				at: from + 0.8 + Double(i) * 0.15, stagger: 0.05, dur: 0.8, kern: -0.5)
		}
		let cmdLines = s(o, V ? "command_v" : "command", s(o, "command")).components(separatedBy: "\n")
		let keys = (o["keys"] as? [Double]) ?? []
		var n = keys.filter { t >= $0 }.count
		let cf = font(V ? 60 : 40, .regular, .mono)
		let lh: CGFloat = V ? 84 : 56
		let cy: CGFloat = V ? 1080 : 640
		let fw = cmdLines.map { width($0, cf) }.max() ?? 0
		let box = CGRect(x: CW / 2 - fw / 2 - 40, y: cy - (V ? 76 : 56), width: fw + 80, height: CGFloat(cmdLines.count - 1) * lh + (V ? 110 : 84))
		let ba = inOutCubic(prog(t, from + 1.3, 0.5))
		save {
			setAlpha(ba)
			fill(box, CGColor(srgbRed: 0.07, green: 0.067, blue: 0.06, alpha: 0.85), radius: 16)
			stroke(box, C("text", 0.14), radius: 16, width: 1.5)
			var cx = box.minX + 40
			for (i, l) in cmdLines.enumerated() {
				let shown = String(l.prefix(max(0, n)))
				n -= l.count
				let base = cy + CGFloat(i) * lh
				cx = box.minX + 40
				if shown.isEmpty { continue }
				if shown.hasPrefix("$") { cx += text("$", cx, base, cf, C("accent")); cx += text(String(shown.dropFirst()), cx, base, cf, C("text")) }
				else { cx += text(shown, cx, base, cf, C("text")) }
				if n <= 0 || i == cmdLines.count - 1 {
					if n < 0 || Int(t * 2) % 2 == 0 { fill(CGRect(x: cx + 3, y: base - (V ? 46 : 30), width: 3, height: V ? 58 : 38), C("text")) }
					break
				}
			}
		}
		let ua = inOutCubic(prog(t, d(o, "url_at"), 0.6))
		let urls = s(o, V ? "url_v" : "url", s(o, "url")).components(separatedBy: "\n")
		let uy = box.maxY + (V ? 120 : 84)
		for (i, u) in urls.enumerated() {
			text(u, CW / 2, uy + CGFloat(i) * (V ? 84 : 50) + (1 - ua) * 12, font(V ? 64 : 40, .medium), C("text"), align: 0.5, alpha: ua)
		}
		let da = inOutCubic(prog(t, d(o, "url_at") + 0.4, 0.6))
		let dl = s(o, V ? "disclaimer_v" : "disclaimer", s(o, "disclaimer")).components(separatedBy: "\n")
		for (i, l) in dl.enumerated() {
			text(l, CW / 2, (V ? 1680 : 1010) + CGFloat(i) * (V ? 84 : 34), font(V ? 62 : 22, .regular), C("muted"), align: 0.5, alpha: da)
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
		// Dissolves: a scene with `fade_in` comes up over the one before it (which stays whole underneath), so beats
		// hand over picture to picture, never through an empty canvas.
		let fi = d(sc, "fade_in"), fo = d(sc, "fade_out")
		let sa = (fi > 0 ? inOutCubic(prog(t, from, fi)) : 1) * (fo > 0 ? 1 - inOutCubic(prog(t, to - fo, fo)) : 1)
		ctx.saveGState(); let a0 = alphaNow; setAlpha(sa); defer { ctx.restoreGState(); alphaNow = a0 }
		switch s(sc, "type") {
		case "make": sceneMake(sc, t)
		case "chat": sceneChat(sc, t)
		case "mcchat": sceneMCChat(sc, t)
		case "mcmonitor": framed(sc, t) { sceneMCMonitor(sc, t) }
		case "t3": sceneT3(sc, t)
		case "card": sceneCard(sc, t)
		case "endmodern": sceneEndModern(sc, t)
		case "mcvoice": framed(sc, t) { sceneMCVoice(sc, t) }
		case "mcedit": framed(sc, t) { sceneMCEdit(sc, t) }
		case "mcscores": framed(sc, t) { sceneMCScores(sc, t) }
		case "mcfilm": framed(sc, t) { sceneMCFilm(sc, t) }
		case "mcreel": sceneMCReel(sc, t)
		case "mcend": sceneMCEnd(sc, t)
		case "monitor": sceneMonitor(sc, t)
		case "timeline": sceneTimeline(sc, t)
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
