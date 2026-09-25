// Phone number, then the 6-digit code. Same two steps for new and returning
// people. In dev the code is printed in the server's terminal, not texted.

import SwiftUI

struct SignInView: View {
    @Environment(AppModel.self) private var model

    @State private var phone = ""
    @State private var code = ""
    @State private var codeSent = false
    @State private var working = false
    @State private var error: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 28) {
                VStack(alignment: .leading, spacing: 10) {
                    Image(systemName: "party.popper.fill")
                        .font(.system(size: 52))
                        .foregroundStyle(Theme.hot)
                        .shadow(color: Theme.pink.opacity(0.6), radius: 20)
                    Text("House\nParty")
                        .font(.system(size: 64, weight: .black, design: .rounded))
                        .foregroundStyle(Theme.hot)
                        .lineSpacing(-12)
                    Text("Find your people. Throw the party.")
                        .font(.title3.weight(.medium))
                        .foregroundStyle(Theme.textDim)
                }
                .padding(.top, 60)

                VStack(alignment: .leading, spacing: 10) {
                    SectionLabel(codeSent ? "Code sent to" : "Your phone number")
                    TextField("", text: $phone, prompt: Text("+1 415 555 0100").foregroundStyle(Theme.textDim))
                        .keyboardType(.phonePad)
                        .textContentType(.telephoneNumber)
                        .font(.title3.weight(.semibold))
                        .disabled(codeSent)
                        .fieldStyle()
                    if !codeSent {
                        Text("Include your country code. We'll text you a code.")
                            .font(.footnote)
                            .foregroundStyle(Theme.textDim)
                    }
                }

                if codeSent {
                    VStack(alignment: .leading, spacing: 10) {
                        SectionLabel("The 6-digit code")
                        TextField("", text: $code, prompt: Text("••••••").foregroundStyle(Theme.textDim))
                            .keyboardType(.numberPad)
                            .textContentType(.oneTimeCode)
                            .font(.system(size: 28, weight: .bold, design: .monospaced))
                            .tracking(8)
                            .fieldStyle()
                    }
                    .transition(.move(edge: .bottom).combined(with: .opacity))
                }

                ErrorText(text: error)

                VStack(spacing: 14) {
                    Button(codeSent ? "Let me in" : "Text me a code", action: submit)
                        .buttonStyle(.hot)
                        .disabled(working || (codeSent ? code.count < 4 : phone.count < 7))
                    if codeSent {
                        Button("Use a different number") {
                            withAnimation { codeSent = false }
                            code = ""
                            error = nil
                        }
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(Theme.textDim)
                    }
                }
            }
            .padding(24)
        }
        .partyScreen()
        .animation(.smooth, value: codeSent)
    }

    private func submit() {
        working = true
        error = nil
        Task {
            defer { working = false }
            do {
                if codeSent {
                    try await model.verify(phone: phone, code: code)
                } else {
                    try await model.sendCode(to: phone)
                    codeSent = true
                }
            } catch {
                self.error = error.localizedDescription
            }
        }
    }
}
