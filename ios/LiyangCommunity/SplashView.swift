import SwiftUI

/// 启动页：浅色渐变 + 「立洋社区」文字（与安卓版一致，不放图标）
struct SplashView: View {
    var body: some View {
        ZStack {
            LinearGradient(
                colors: [
                    Color(red: 0.874, green: 0.922, blue: 1.0),
                    Color.white,
                ],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            VStack(spacing: 8) {
                Text("立洋社区")
                    .font(.system(size: 28, weight: .bold))
                    .foregroundColor(Color(red: 0.04, green: 0.31, blue: 0.82))
                Text("校园社区")
                    .font(.footnote)
                    .kerning(3)
                    .foregroundColor(Color(red: 0.42, green: 0.53, blue: 0.71))
                ProgressView()
                    .tint(Color(red: 0.04, green: 0.31, blue: 0.82))
                    .padding(.top, 32)
            }
        }
        .ignoresSafeArea()
    }
}
