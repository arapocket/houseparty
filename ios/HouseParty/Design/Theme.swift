// The look of the app in one place: colors, the background, cards, buttons,
// text fields. Screens use these instead of picking colors themselves, so
// changing the feel of the whole app means editing this file.

import SwiftUI

enum Theme {
    // Night-time party palette: deep purple base, neon accents.
    static let background = Color(hex: 0x0E0A1A)
    static let surface = Color(hex: 0x1A1330)
    static let surfaceHigh = Color(hex: 0x261C44)
    static let stroke = Color.white.opacity(0.08)

    static let text = Color(hex: 0xF5F0FF)
    static let textDim = Color(hex: 0xA99BC9)

    static let pink = Color(hex: 0xFF4D8D)
    static let orange = Color(hex: 0xFFA94D)
    static let violet = Color(hex: 0x8B6CFF)
    static let mint = Color(hex: 0x3DDC97)
    static let cyan = Color(hex: 0x4CC9F0)
    static let yellow = Color(hex: 0xFFD166)

    /// The signature pink → orange used for primary buttons and headings.
    static let hot = LinearGradient(
        colors: [pink, orange], startPoint: .topLeading, endPoint: .bottomTrailing
    )

    /// Every interest gets its own color, the same everywhere and for
    /// everyone ("Ramen" is always the same color).
    static func color(for interest: String) -> Color {
        let palette = [pink, orange, violet, mint, cyan, yellow]
        // A simple, stable hash. Swift's own hashValue changes every launch.
        var hash: UInt32 = 5381
        for scalar in interest.lowercased().unicodeScalars {
            hash = (hash &<< 5) &+ hash &+ scalar.value
        }
        return palette[Int(hash % UInt32(palette.count))]
    }
}

extension Color {
    init(hex: UInt32) {
        self.init(
            red: Double((hex >> 16) & 0xFF) / 255,
            green: Double((hex >> 8) & 0xFF) / 255,
            blue: Double(hex & 0xFF) / 255
        )
    }
}

// MARK: - Background

/// Dark base with two soft colored glows, like light spilling from a party.
struct PartyBackground: View {
    var body: some View {
        ZStack {
            Theme.background
            RadialGradient(
                colors: [Theme.violet.opacity(0.35), .clear],
                center: .topLeading, startRadius: 0, endRadius: 420
            )
            RadialGradient(
                colors: [Theme.pink.opacity(0.22), .clear],
                center: .bottomTrailing, startRadius: 0, endRadius: 460
            )
        }
        .ignoresSafeArea()
    }
}

extension View {
    /// Puts a screen on the party background with the house font and colors.
    func partyScreen() -> some View {
        self
            .scrollContentBackground(.hidden)
            .background(PartyBackground())
            .foregroundStyle(Theme.text)
    }

    /// A rounded panel that groups related things.
    func card(padding: CGFloat = 16) -> some View {
        self
            .padding(padding)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Theme.surface, in: .rect(cornerRadius: 24))
            .overlay(RoundedRectangle(cornerRadius: 24).stroke(Theme.stroke))
    }
}

// MARK: - Text

/// Big heading at the top of a screen, in the hot gradient.
struct ScreenTitle: View {
    let text: String

    var body: some View {
        Text(text)
            .font(.system(size: 38, weight: .heavy, design: .rounded))
            .foregroundStyle(Theme.hot)
            .frame(maxWidth: .infinity, alignment: .leading)
    }
}

/// Small label above a group, like "ABOUT YOU".
struct SectionLabel: View {
    let text: String

    init(_ text: String) { self.text = text }

    var body: some View {
        Text(text.uppercased())
            .font(.caption.weight(.bold))
            .tracking(1.2)
            .foregroundStyle(Theme.textDim)
            .frame(maxWidth: .infinity, alignment: .leading)
    }
}

struct ErrorText: View {
    let text: String?

    var body: some View {
        if let text {
            Label(text, systemImage: "exclamationmark.triangle.fill")
                .font(.subheadline.weight(.medium))
                .foregroundStyle(Theme.pink)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
    }
}

// MARK: - Buttons and fields

/// The main action on a screen: a glowing gradient pill.
struct HotButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var isEnabled

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.headline)
            .foregroundStyle(.white)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 16)
            .background(Theme.hot, in: .capsule)
            .shadow(color: Theme.pink.opacity(isEnabled ? 0.45 : 0), radius: 16, y: 6)
            .opacity(isEnabled ? 1 : 0.4)
            .scaleEffect(configuration.isPressed ? 0.97 : 1)
            .animation(.snappy(duration: 0.15), value: configuration.isPressed)
    }
}

/// A quieter action: dark pill with colored text.
struct SoftButtonStyle: ButtonStyle {
    var tint: Color = Theme.text

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.subheadline.weight(.semibold))
            .foregroundStyle(tint)
            .padding(.vertical, 12)
            .padding(.horizontal, 18)
            .background(Theme.surfaceHigh, in: .capsule)
            .overlay(Capsule().stroke(Theme.stroke))
            .scaleEffect(configuration.isPressed ? 0.96 : 1)
            .animation(.snappy(duration: 0.15), value: configuration.isPressed)
    }
}

extension ButtonStyle where Self == HotButtonStyle {
    static var hot: HotButtonStyle { HotButtonStyle() }
}

extension ButtonStyle where Self == SoftButtonStyle {
    static var soft: SoftButtonStyle { SoftButtonStyle() }
    static func soft(_ tint: Color) -> SoftButtonStyle { SoftButtonStyle(tint: tint) }
}

/// Text field on a dark rounded panel.
struct FieldBackground: ViewModifier {
    func body(content: Content) -> some View {
        content
            .padding(.horizontal, 16)
            .padding(.vertical, 14)
            .background(Theme.surfaceHigh, in: .rect(cornerRadius: 16))
            .overlay(RoundedRectangle(cornerRadius: 16).stroke(Theme.stroke))
    }
}

extension View {
    func fieldStyle() -> some View { modifier(FieldBackground()) }
}
