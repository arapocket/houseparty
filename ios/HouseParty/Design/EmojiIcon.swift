// Turns an emoji into an image, for places that need a picture rather than
// text, like the tab bar. Used for the Match tab's 🤝, since iOS has no
// built-in handshake symbol.

import UIKit

enum EmojiIcon {
    static func image(_ emoji: String, size: CGFloat = 25) -> UIImage {
        let font = UIFont.systemFont(ofSize: size * 0.9)
        let canvas = CGSize(width: size, height: size)
        let drawn = UIGraphicsImageRenderer(size: canvas).image { _ in
            let text = NSAttributedString(string: emoji, attributes: [.font: font])
            let textSize = text.size()
            text.draw(at: CGPoint(
                x: (canvas.width - textSize.width) / 2,
                y: (canvas.height - textSize.height) / 2
            ))
        }
        // Keep its own colors instead of being tinted like the other icons.
        return drawn.withRenderingMode(.alwaysOriginal)
    }
}
