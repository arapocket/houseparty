// Your profile: the "down to party" switch, search radius, interests, and
// signing out or deleting the account.

import SwiftUI

struct ProfileView: View {
    @Environment(AppModel.self) private var model

    @State private var downToParty = false
    @State private var radius = 15.0
    @State private var interests: [String] = []
    @State private var interestsChanged = false
    @State private var confirmingDelete = false
    @State private var error: String?
    @State private var photoNote: String?

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    if let me = model.me {
                        HStack(spacing: 16) {
                            PhotoPickerAvatar(size: 72) { message, isError in
                                if isError { error = message } else { photoNote = message; error = nil }
                            }
                            VStack(alignment: .leading, spacing: 4) {
                                Text([me.firstName, me.age.map(String.init)].compactMap { $0 }.joined(separator: ", "))
                                    .font(.system(size: 30, weight: .heavy, design: Theme.fontDesign))
                                if let hood = me.neighborhood {
                                    Label(hood, systemImage: "mappin.and.ellipse")
                                        .foregroundStyle(Theme.textDim)
                                }
                            }
                        }
                        .padding(.top, 12)

                        if me.photoInReview || photoNote != nil {
                            Label(
                                photoNote ?? "Your new photo is being checked. Your old one stays up until then.",
                                systemImage: "hourglass"
                            )
                            .font(.footnote)
                            .foregroundStyle(Theme.yellow)
                        }
                    }

                    Toggle(isOn: $downToParty) {
                        VStack(alignment: .leading, spacing: 2) {
                            Label("Down to party", systemImage: "flame.fill")
                                .font(.headline)
                                .foregroundStyle(downToParty ? Theme.mint : Theme.text)
                            Text("Hosts see this on your profile.")
                                .font(.footnote)
                                .foregroundStyle(Theme.textDim)
                        }
                    }
                    .tint(Theme.mint)
                    .card()
                    .onChange(of: downToParty) { _, on in
                        if on != model.me?.downToParty { save(ProfileUpdate(downToParty: on)) }
                    }

                    VStack(alignment: .leading, spacing: 12) {
                        HStack {
                            SectionLabel("Match radius")
                            Text("\(Int(radius)) km")
                                .font(.headline)
                                .foregroundStyle(Theme.hot)
                        }
                        Slider(value: $radius, in: 1...50, step: 1) { editing in
                            if !editing { save(ProfileUpdate(searchRadiusKm: Int(radius))) }
                        }
                    }
                    .card()

                    VStack(alignment: .leading, spacing: 12) {
                        SectionLabel("Your interests")
                        InterestsEditor(interests: $interests)
                            .onChange(of: interests) { interestsChanged = interests != model.me?.interests }
                        if interestsChanged {
                            Button("Save interests") {
                                save(ProfileUpdate(), interests: interests)
                            }
                            .buttonStyle(.hot)
                        }
                    }
                    .card()

                    ErrorText(text: error)

                    HStack(spacing: 12) {
                        Button("Sign out") { model.signOut() }
                            .buttonStyle(.soft)
                        Button("Delete account") { confirmingDelete = true }
                            .buttonStyle(.soft(Theme.pink))
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.top, 8)
                }
                .padding(20)
            }
            .scrollDismissesKeyboard(.interactively)
            .partyScreen()
            .toolbarVisibility(.hidden, for: .navigationBar)
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
        interestsChanged = false
    }

    private func save(_ changes: ProfileUpdate, interests: [String]? = nil) {
        Task {
            do {
                try await model.saveProfile(changes, interests: interests)
                interestsChanged = false
                error = nil
            } catch {
                self.error = error.localizedDescription
            }
        }
    }
}
