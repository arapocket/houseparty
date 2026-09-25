// Getting a picked photo ready to upload: make sure there's a face in it,
// then shrink it and turn it into a JPEG.
//
// The server shrinks and cleans it again anyway (and strips the location),
// but doing it here too means a 12-megapixel photo doesn't have to crawl up
// over a phone connection first.

import UIKit
import Vision

enum PhotoPrep {
    enum Problem: LocalizedError {
        case unreadable
        case noFace

        var errorDescription: String? {
            switch self {
            case .unreadable: "Couldn't open that photo. Try another one."
            case .noFace: "Use a photo of you. We couldn't find a face in that one."
            }
        }
    }

    static func prepare(_ data: Data) async throws -> Data {
        guard let image = UIImage(data: data), let cgImage = image.cgImage else {
            throw Problem.unreadable
        }
        guard await hasFace(cgImage, orientation: image.imageOrientation) else {
            throw Problem.noFace
        }

        guard let jpeg = shrink(image, longestSide: 1600).jpegData(compressionQuality: 0.85) else {
            throw Problem.unreadable
        }
        return jpeg
    }

    /// Apple's on-device face finder. Free, fast, and nothing leaves the
    /// phone for it. If the finder itself can't run (it doesn't in the
    /// simulator, and could fail on an old phone), let the photo through:
    /// this is a helpful nudge, and the server does the real checking.
    private static func hasFace(_ cgImage: CGImage, orientation: UIImage.Orientation) async -> Bool {
        do {
            let faces = try await DetectFaceRectanglesRequest().perform(
                on: cgImage, orientation: CGImagePropertyOrientation(orientation)
            )
            return !faces.isEmpty
        } catch {
            return true
        }
    }

    private static func shrink(_ image: UIImage, longestSide: CGFloat) -> UIImage {
        let scale = min(1, longestSide / max(image.size.width, image.size.height))
        guard scale < 1 else { return image }
        let size = CGSize(width: image.size.width * scale, height: image.size.height * scale)
        return UIGraphicsImageRenderer(size: size).image { _ in
            image.draw(in: CGRect(origin: .zero, size: size))
        }
    }
}

extension CGImagePropertyOrientation {
    /// UIKit and Vision describe "which way up" differently.
    init(_ orientation: UIImage.Orientation) {
        switch orientation {
        case .up: self = .up
        case .down: self = .down
        case .left: self = .left
        case .right: self = .right
        case .upMirrored: self = .upMirrored
        case .downMirrored: self = .downMirrored
        case .leftMirrored: self = .leftMirrored
        case .rightMirrored: self = .rightMirrored
        @unknown default: self = .up
        }
    }
}
