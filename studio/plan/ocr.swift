// Reads the words on a drawing with macOS's own text recognition (Vision), and prints them as JSON:
// [{"text", "confidence", "box": [x, y, width, height]}] in pixels, with y from the top.
// swift ocr.swift IMAGE [X Y W H SCALE]   (optional: read only that part, enlarged SCALE times)
import Foundation
import Vision
import AppKit

let path = CommandLine.arguments[1]
guard let image = NSImage(contentsOfFile: path),
      let full = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
    FileHandle.standardError.write("can't read \(path)\n".data(using: .utf8)!)
    exit(1)
}
var cg = full
var ox = 0.0, oy = 0.0, k = 1.0
let a = CommandLine.arguments
if a.count >= 7, let x = Double(a[2]), let y = Double(a[3]), let cw = Double(a[4]), let ch = Double(a[5]), let sc = Double(a[6]),
   let part = full.cropping(to: CGRect(x: x, y: y, width: cw, height: ch)) {
    let W = Int(cw * sc), H = Int(ch * sc)
    let ctx = CGContext(data: nil, width: W, height: H, bitsPerComponent: 8, bytesPerRow: 0,
                        space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue)!
    ctx.interpolationQuality = .high
    ctx.draw(part, in: CGRect(x: 0, y: 0, width: W, height: H))
    cg = ctx.makeImage()!
    ox = x; oy = y; k = sc
}
let w = Double(cg.width), h = Double(cg.height)
let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.usesLanguageCorrection = false
request.recognitionLanguages = ["en-US"]
request.minimumTextHeight = 0.004
try VNImageRequestHandler(cgImage: cg, options: [:]).perform([request])
var out: [[String: Any]] = []
for obs in request.results ?? [] {
    guard let best = obs.topCandidates(1).first else { continue }
    let b = obs.boundingBox
    out.append(["text": best.string, "confidence": Double(best.confidence),
                "box": [ox + b.minX * w / k, oy + (1 - b.maxY) * h / k, b.width * w / k, b.height * h / k]])
}
let data = try JSONSerialization.data(withJSONObject: out, options: [.prettyPrinted])
print(String(data: data, encoding: .utf8)!)
