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
        NavigationStack {
            Form {
                Section {
                    TextField("+1 415 555 0100", text: $phone)
                        .keyboardType(.phonePad)
                        .textContentType(.telephoneNumber)
                        .disabled(codeSent)
                } header: {
                    Text("Your phone number")
                } footer: {
                    Text("Include your country code. We'll text you a code.")
                }

                if codeSent {
                    Section("The code we texted you") {
                        TextField("123456", text: $code)
                            .keyboardType(.numberPad)
                            .textContentType(.oneTimeCode)
                    }
                }

                if let error {
                    Text(error).foregroundStyle(.red)
                }

                Section {
                    Button(codeSent ? "Sign in" : "Text me a code", action: submit)
                        .disabled(working || (codeSent ? code.count < 4 : phone.count < 7))
                    if codeSent {
                        Button("Use a different number") {
                            codeSent = false
                            code = ""
                            error = nil
                        }
                    }
                }
            }
            .navigationTitle("House Party")
        }
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
