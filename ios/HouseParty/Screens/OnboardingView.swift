// Setting up your profile after the first sign-in: name, birthday (21+),
// neighborhood, location, interests.

import SwiftUI

struct OnboardingView: View {
    @Environment(AppModel.self) private var model

    @State private var firstName = ""
    @State private var birthday = Calendar.current.date(byAdding: .year, value: -25, to: .now)!
    @State private var neighborhood = ""
    @State private var interests: [String] = []
    @State private var working = false
    @State private var error: String?

    var body: some View {
        NavigationStack {
            Form {
                Section("About you") {
                    TextField("First name", text: $firstName)
                        .textContentType(.givenName)
                    DatePicker("Birthday", selection: $birthday, displayedComponents: .date)
                    TextField("Neighborhood", text: $neighborhood)
                }

                Section {
                    InterestsEditor(interests: $interests)
                } header: {
                    Text("Interests")
                } footer: {
                    Text("Be specific: \"Kid A era Radiohead\" beats \"music\". Up to 12.")
                }

                if let error {
                    Text(error).foregroundStyle(.red)
                }

                Section {
                    Button("Done", action: save)
                        .disabled(working || firstName.isEmpty || interests.isEmpty)
                } footer: {
                    Text("We'll ask for your location so we can find people nearby. "
                        + "Nobody sees where you are, only roughly how far away.")
                }
            }
            .navigationTitle("Your profile")
        }
    }

    private func save() {
        working = true
        error = nil
        Task {
            defer { working = false }
            do {
                let spot = try await Location.current()
                let changes = ProfileUpdate(
                    firstName: firstName.trimmingCharacters(in: .whitespaces),
                    birthdate: birthday.birthdateString,
                    neighborhood: neighborhood.isEmpty ? nil : neighborhood,
                    latitude: spot.latitude,
                    longitude: spot.longitude,
                    downToParty: true
                )
                try await model.saveProfile(changes, interests: interests)
            } catch {
                self.error = error.localizedDescription
            }
        }
    }
}

/// Type an interest, pick from popular spellings as you go, remove with a swipe.
struct InterestsEditor: View {
    @Environment(AppModel.self) private var model
    @Binding var interests: [String]

    @State private var draft = ""
    @State private var suggestions: [InterestSuggestion] = []

    private let maxInterests = 12
    private let maxLength = 40

    var body: some View {
        ForEach(interests, id: \.self) { interest in
            Text(interest)
        }
        .onDelete { interests.remove(atOffsets: $0) }

        if interests.count < maxInterests {
            TextField("Add an interest", text: $draft)
                .onSubmit { add(draft) }
                .onChange(of: draft) { _, text in
                    if text.count > maxLength { draft = String(text.prefix(maxLength)) }
                }
                // Re-runs (and cancels the last run) every time the text changes.
                .task(id: draft) { await loadSuggestions(for: draft) }

            // Suggesting existing spellings is how wording converges, so
            // "radiohead" and "Radiohead!" end up as one interest.
            ForEach(suggestions, id: \.display) { suggestion in
                Button {
                    add(suggestion.display)
                } label: {
                    LabeledContent(suggestion.display, value: "\(suggestion.usageCount)")
                }
            }
        }
    }

    private func add(_ text: String) {
        let clean = text.trimmingCharacters(in: .whitespaces)
        guard clean.count >= 2,
              !interests.contains(where: { $0.caseInsensitiveCompare(clean) == .orderedSame })
        else { return }
        interests.append(clean)
        draft = ""
        suggestions = []
    }

    private func loadSuggestions(for text: String) async {
        guard text.count >= 2 else {
            suggestions = []
            return
        }
        try? await Task.sleep(for: .milliseconds(250))  // wait until they pause typing
        guard !Task.isCancelled else { return }
        let found = (try? await model.api.suggestInterests(text)) ?? []
        suggestions = found.filter { !interests.contains($0.display) }
    }
}
