// The acid-house smiley: yellow face, black oval eyes, a wide grin with
// little dimples at the ends. Drawn with shapes rather than an image so it
// stays crisp at any size. It's the app's "like".

import SwiftUI

struct AcidSmiley: View {
    var size: CGFloat = 22
    /// Spins slowly, for big celebratory moments.
    var spinning = false

    static let yellow = Color(hex: 0xFFE14D)

    @State private var angle: Double = 0

    var body: some View {
        ZStack {
            Circle().fill(Self.yellow)
            Circle().stroke(.black, lineWidth: max(1, size * 0.05))

            // Eyes: tall ovals.
            HStack(spacing: size * 0.2) {
                Capsule().fill(.black).frame(width: size * 0.11, height: size * 0.27)
                Capsule().fill(.black).frame(width: size * 0.11, height: size * 0.27)
            }
            .offset(y: -size * 0.13)

            Grin()
                .stroke(.black, style: StrokeStyle(lineWidth: max(1, size * 0.07), lineCap: .round))
                .frame(width: size * 0.64, height: size * 0.28)
                .offset(y: size * 0.17)
        }
        .frame(width: size, height: size)
        .rotationEffect(.degrees(angle))
        .onAppear {
            guard spinning else { return }
            withAnimation(.linear(duration: 6).repeatForever(autoreverses: false)) { angle = 360 }
        }
        .accessibilityHidden(true)
    }
}

/// A smile curve with a short upward tick at each end.
private struct Grin: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()
        let tick = rect.width * 0.1
        path.move(to: CGPoint(x: rect.minX - tick * 0.3, y: rect.minY - tick * 0.6))
        path.addLine(to: CGPoint(x: rect.minX + tick * 0.2, y: rect.minY + tick * 0.2))
        path.move(to: CGPoint(x: rect.minX, y: rect.minY))
        path.addQuadCurve(
            to: CGPoint(x: rect.maxX, y: rect.minY),
            control: CGPoint(x: rect.midX, y: rect.maxY * 1.7)
        )
        path.move(to: CGPoint(x: rect.maxX + tick * 0.3, y: rect.minY - tick * 0.6))
        path.addLine(to: CGPoint(x: rect.maxX - tick * 0.2, y: rect.minY + tick * 0.2))
        return path
    }
}

#Preview {
    HStack(spacing: 20) {
        AcidSmiley(size: 22)
        AcidSmiley(size: 60)
        AcidSmiley(size: 120, spinning: true)
    }
    .padding()
    .background(Theme.background)
}
