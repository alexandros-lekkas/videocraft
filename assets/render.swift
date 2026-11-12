// Renders an SVG to a PNG with AppKit (macOS 14+ reads SVG natively): swiftc -O assets/render.swift -o /tmp/vc-render
// then /tmp/vc-render assets/banner.svg assets/banner.png 1280 320. Used by assets/make_art.py when swiftc exists.
import AppKit
let args = CommandLine.arguments
let src = URL(fileURLWithPath: args[1]); let out = URL(fileURLWithPath: args[2])
let w = Int(args[3])!, h = Int(args[4])!
guard let img = NSImage(contentsOf: src) else { print("cannot load"); exit(1) }
let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: w, pixelsHigh: h, bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
rep.size = NSSize(width: w, height: h)
NSGraphicsContext.saveGraphicsState()
NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
img.draw(in: NSRect(x: 0, y: 0, width: w, height: h))
NSGraphicsContext.restoreGraphicsState()
try! rep.representation(using: .png, properties: [:])!.write(to: out)
print("ok", w, h)
