// Your profile: the "down to party" switch, search radius, interests, and
// signing out or deleting the account.

import SwiftUI

struct ProfileView: View {
    @Environment(AppModel.self) private var model

    @State private var downToParty = false
    @State private var radius = 15.0
    @State private var interests: [String] = []
    @State private var confirmingDelete = false
    @State private var error: String?

    var body: some View {
        NavigationStack {
            Form {
                if let me = model.me {
                    Section {
                        LabeledContent("Name", value: me.firstName ?? "")
                        if let age = me.age { LabeledContent("Age", value: "\(age)") }
                        LabeledContent("Neighborhood", value: me.neighborhood ?? "Not set")
                    }
                }

                Section {
                    Toggle("Down to party", isOn: $downToParty)
                        .onChange(of: downToParty) { _, on in save(ProfileUpdate(downToParty: on)) }
                }

                Section {
                    Slider(value: $radius, in: 1...50, step: 1) { editing in
                        if !editing { save(ProfileUpdate(searchRadiusKm: Int(radius))) }
                    }
                } header: {
                    Text("Discover people within \(Int(radius)) km")
                }

                Section("Interests") {
                    InterestsEditor(interests: $interests)
                    Button("Save interests") { save(ProfileUpdate(), interests: interests) }
                }

                if let error {
                    Text(error).foregroundStyle(.red)
                }

                Section {
                    Button("Sign out") { model.signOut() }
                    Button("Delete account", role: .destructive) { confirmingDelete = true }
                }
            }
            .navigationTitle("Me")
            .onAppear(perform: fillFromMe)
            .confirmationDialog(
                "Delete your account?",
                isPresented: $confirmingDelete,
                titleVisibility: .visible
            ) {
                Button("Delete for good", role: .destructive) {
                    Task {
                        do { try await model.deleteAccount() } catch {
                            self.error = error.localizedDescription
                        }
                    }
                }
            } message: {
                Text("Your profile, interests and upcoming parties go away. This can't be undone.")
            }
        }
    }

    private func fillFromMe() {
        guard let me = model.me else { return }
        downToParty = me.downToParty
        radius = Double(me.searchRadiusKm)
        interests = me.interests
    }

    private func save(_ changes: ProfileUpdate, interests: [String]? = nil) {
        Task {
            do {
                try await model.saveProfile(changes, interests: interests)
                error = nil
            } catch {
                self.error = error.localizedDescription
            }
        }
    }
}
