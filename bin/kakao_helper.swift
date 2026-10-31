// 인터뷰 실행기 보조 도구 (macOS). 빌드: swiftc -O bin/kakao_helper.swift -o .coord/bin/kakao_helper
// 사용:
//   kakao_helper windows              → 카카오톡 창 목록 JSON [{id,title,x,y,w,h,layer}] (제목은 '화면 및 시스템 오디오 녹음' 권한이 있어야 보인다)
//   kakao_helper ocr <이미지 경로>      → 인식한 줄 JSON [{text,x,y,w,h,conf}] (위→아래 정렬, y는 위 기준 0~1)
// 키 입력·클릭은 하지 않는다(전송은 interview_runner.py가 사용자 승인 후 osascript로 한다).
import Foundation
import CoreGraphics
import Vision
import AppKit

func emit(_ obj: Any) {
    let data = try! JSONSerialization.data(withJSONObject: obj, options: [.sortedKeys])
    FileHandle.standardOutput.write(data)
    FileHandle.standardOutput.write("\n".data(using: .utf8)!)
}

let args = CommandLine.arguments
guard args.count >= 2 else {
    FileHandle.standardError.write("usage: kakao_helper windows | ocr <image>\n".data(using: .utf8)!)
    exit(2)
}

switch args[1] {
case "windows":
    let opts: CGWindowListOption = [.optionOnScreenOnly, .excludeDesktopElements]
    let list = (CGWindowListCopyWindowInfo(opts, kCGNullWindowID) as? [[String: Any]]) ?? []
    var out: [[String: Any]] = []
    for w in list {
        let owner = w[kCGWindowOwnerName as String] as? String ?? ""
        if !owner.lowercased().contains("kakao") && owner != "카카오톡" { continue }
        let b = w[kCGWindowBounds as String] as? [String: Any] ?? [:]
        out.append([
            "id": w[kCGWindowNumber as String] as? Int ?? 0,
            "title": w[kCGWindowName as String] as? String ?? "",
            "owner": owner,
            "layer": w[kCGWindowLayer as String] as? Int ?? 0,
            "x": b["X"] as? Double ?? 0, "y": b["Y"] as? Double ?? 0,
            "w": b["Width"] as? Double ?? 0, "h": b["Height"] as? Double ?? 0,
        ])
    }
    emit(out)
case "ocr":
    guard args.count >= 3, let img = NSImage(contentsOfFile: args[2]),
          let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
        FileHandle.standardError.write("cannot load image\n".data(using: .utf8)!)
        exit(1)
    }
    let req = VNRecognizeTextRequest()
    req.recognitionLevel = .accurate
    req.usesLanguageCorrection = true
    req.recognitionLanguages = ["ko-KR", "en-US"]
    let handler = VNImageRequestHandler(cgImage: cg, options: [:])
    do { try handler.perform([req]) } catch {
        FileHandle.standardError.write("ocr failed: \(error)\n".data(using: .utf8)!)
        exit(1)
    }
    var lines: [[String: Any]] = []
    for o in req.results ?? [] {
        guard let c = o.topCandidates(1).first else { continue }
        let r = o.boundingBox  // 원점이 왼쪽 아래, 0~1
        lines.append(["text": c.string, "conf": Double(c.confidence),
                      "x": Double(r.minX), "y": Double(1 - r.maxY), "w": Double(r.width), "h": Double(r.height)])
    }
    lines.sort { (($0["y"] as! Double), ($0["x"] as! Double)) < (($1["y"] as! Double), ($1["x"] as! Double)) }
    emit(lines)
default:
    FileHandle.standardError.write("unknown command\n".data(using: .utf8)!)
    exit(2)
}
