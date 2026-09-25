// Your avatar with a camera badge. Tap it to choose a new profile photo.

import PhotosUI
import SwiftUI

struct PhotoPickerAvatar: View {
    @Environment(AppModel.self) private var model

    var size: CGFloat = 72
    /// Tells the screen what happened, in words it can show.
    var onMessage: (String?, Bool) -> Void = { _, _ in }

    @State private var picked: PhotosPickerItem?
    @State private var uploading = false

    var body: some View {
        PhotosPicker(selection: $picked, matching: .images) {
            ZStack(alignment: .bottomTrailing) {
                Avatar(url: model.me?.photoUrl, name: model.me?.firstName, size: size)
                    .overlay {
                        if uploading {
                            ProgressView().tint(.white)
                                .frame(width: size, height: size)
                                .background(.black.opacity(0.45), in: .circle)
                        }
                    }
                Image(systemName: "camera.fill")
                    .font(.system(size: size * 0.16, weight: .bold))
                    .foregroundStyle(.white)
                    .padding(size * 0.09)
                    .background(Theme.hot, in: .circle)
                    .overlay(Circle().stroke(Theme.background, lineWidth: 2))
            }
        }
        .buttonStyle(.plain)
        .disabled(uploading)
        .accessibilityLabel("Change profile photo")
        .onChange(of: picked) { _, item in
            guard let item else { return }
            Task { await upload(item) }
        }
    }

    private func upload(_ item: PhotosPickerItem) async {
        uploading = true
        defer {
            uploading = false
            picked = nil
        }
        do {
            guard let data = try await item.loadTransferable(type: Data.self) else {
                throw PhotoPrep.Problem.unreadable
            }
            let jpeg = try await PhotoPrep.prepare(data)
            let live = try await model.uploadPhoto(jpeg: jpeg)
            onMessage(live ? nil : "Your new photo is being checked. Your old one stays up until then.", false)
        } catch {
            onMessage(error.localizedDescription, true)
        }
    }
}
