// Small reusable pieces: interest chips, avatars, the chip layout.

import SwiftUI

/// One interest as a colored pill. Shared interests glow; others are outlined.
struct InterestChip: View {
    let text: String
    var shared = true
    var onRemove: (() -> Void)?

    var body: some View {
        let color = Theme.color(for: text)
        HStack(spacing: 6) {
            Text(text)
            if let onRemove {
                Button(action: onRemove) {
                    Image(systemName: "xmark").font(.caption2.weight(.bold))
                }
                .accessibilityLabel("Remove \(text)")
            }
        }
        .font(.subheadline.weight(.semibold))
        .padding(.horizontal, 12)
        .padding(.vertical, 7)
        .foregroundStyle(shared ? Theme.background : color)
        .background(shared ? color : color.opacity(0.12), in: .capsule)
        .overlay(Capsule().stroke(color.opacity(shared ? 0 : 0.5)))
    }
}

/// Lays chips out left to right, wrapping onto new lines like words in a
/// paragraph.
struct FlowLayout: Layout {
    var spacing: CGFloat = 8

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let rows = arrange(subviews, width: proposal.width ?? .infinity)
        let width = rows.map(\.width).max() ?? 0
        let height = rows.map(\.height).reduce(0, +) + spacing * CGFloat(max(rows.count - 1, 0))
        return CGSize(width: width, height: height)
    }

    func placeSubviews(
        in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()
    ) {
        var y = bounds.minY
        for row in arrange(subviews, width: bounds.width) {
            var x = bounds.minX
            for index in row.items {
                let size = subviews[index].sizeThatFits(.unspecified)
                subviews[index].place(at: CGPoint(x: x, y: y), proposal: ProposedViewSize(size))
                x += size.width + spacing
            }
            y += row.height + spacing
        }
    }

    private struct Row {
        var items: [Int] = []
        var width: CGFloat = 0
        var height: CGFloat = 0
    }

    private func arrange(_ subviews: Subviews, width: CGFloat) -> [Row] {
        var rows: [Row] = [Row()]
        for index in subviews.indices {
            let size = subviews[index].sizeThatFits(.unspecified)
            let needed = rows[rows.count - 1].items.isEmpty ? size.width : size.width + spacing
            if rows[rows.count - 1].width + needed > width, !rows[rows.count - 1].items.isEmpty {
                rows.append(Row())
            }
            let extra = rows[rows.count - 1].items.isEmpty ? size.width : size.width + spacing
            rows[rows.count - 1].items.append(index)
            rows[rows.count - 1].width += extra
            rows[rows.count - 1].height = max(rows[rows.count - 1].height, size.height)
        }
        return rows
    }
}

/// A row of interest chips that wraps.
struct ChipCloud: View {
    let interests: [String]
    var sharedWithMe: Set<String>? = nil

    var body: some View {
        FlowLayout {
            ForEach(interests, id: \.self) { interest in
                InterestChip(text: interest, shared: sharedWithMe?.contains(interest) ?? true)
            }
        }
    }
}

/// Round photo with a gradient ring. Shows a colored initial when there's
/// no photo yet.
struct Avatar: View {
    let url: String?
    var name: String? = nil
    var size: CGFloat = 52

    var body: some View {
        AsyncImage(url: url.flatMap(URL.init(string:))) { image in
            image.resizable().scaledToFill()
        } placeholder: {
            let initial = name?.first.map(String.init) ?? "?"
            Text(initial)
                .font(.system(size: size * 0.42, weight: .heavy, design: .rounded))
                .foregroundStyle(.white)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(
                    LinearGradient(
                        colors: [Theme.color(for: name ?? "?"), Theme.violet],
                        startPoint: .topLeading, endPoint: .bottomTrailing
                    )
                )
        }
        .frame(width: size, height: size)
        .clipShape(Circle())
        .padding(3)
        .overlay(Circle().stroke(Theme.hot, lineWidth: 2))
    }
}

/// A small labelled capsule, e.g. "down to party" or "Introduced by a friend".
struct Badge: View {
    let text: String
    var systemImage: String? = nil
    var color: Color = Theme.mint

    var body: some View {
        HStack(spacing: 4) {
            if let systemImage { Image(systemName: systemImage) }
            Text(text)
        }
        .font(.caption.weight(.bold))
        .padding(.horizontal, 10)
        .padding(.vertical, 5)
        .foregroundStyle(color)
        .background(color.opacity(0.15), in: .capsule)
    }
}

/// An empty state that matches the rest of the app.
struct EmptyState: View {
    let title: String
    let message: String
    let systemImage: String

    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: systemImage)
                .font(.system(size: 44, weight: .semibold))
                .foregroundStyle(Theme.hot)
            Text(title).font(.title3.weight(.bold))
            Text(message)
                .font(.subheadline)
                .foregroundStyle(Theme.textDim)
                .multilineTextAlignment(.center)
        }
        .padding(32)
        .frame(maxWidth: .infinity)
    }
}
