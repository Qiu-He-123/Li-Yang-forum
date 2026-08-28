import SwiftUI

/// 维护面板：与安卓版布局一致（顶栏 + 公告内容 + 重新连接/联系管理员/退出）
struct OfflineView: View {
    @Binding var noticeText: String
    var onRetry: () -> Void
    var onContact: () -> Void
    @State private var showCopied = false

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text("立洋社区")
                    .font(.headline)
                    .foregroundColor(.white)
                Spacer()
                Text("服务维护中")
                    .font(.subheadline)
                    .foregroundColor(.white.opacity(0.85))
            }
            .padding(.horizontal, 16)
            .frame(height: 52)
            .background(Color(red: 0.09, green: 0.47, blue: 1.0))

            ScrollView {
                VStack(spacing: 8) {
                    Text("服务器维护更新中")
                        .font(.title2.bold())
                        .foregroundColor(Color(red: 0.12, green: 0.14, blue: 0.16))
                    Text("暂时无法连接到服务器，可能是正在维护或升级。维护完成后会自动恢复。")
                        .font(.footnote)
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                    Text(noticeText)
                        .font(.subheadline)
                        .foregroundColor(Color(red: 0.2, green: 0.2, blue: 0.2))
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.top, 16)
                }
                .padding(24)
            }

            HStack(spacing: 12) {
                Button("重新连接", action: onRetry)
                    .buttonStyle(PillButtonStyle(
                        background: .white,
                        foreground: Color(red: 0.09, green: 0.47, blue: 1.0),
                        border: Color(red: 0.09, green: 0.47, blue: 1.0)
                    ))
                Button("联系管理员") {
                    UIPasteboard.general.string = AppConfig.contactQQ
                    showCopied = true
                    onContact()
                }
                .buttonStyle(PillButtonStyle(
                    background: Color(red: 0.09, green: 0.47, blue: 1.0),
                    foreground: .white,
                    border: .clear
                ))
                Button("退出") { exit(0) }
                    .buttonStyle(PillButtonStyle(
                        background: Color(red: 0.91, green: 0.92, blue: 0.94),
                        foreground: .gray,
                        border: .clear
                    ))
            }
            .padding(16)
        }
        .background(Color(red: 0.956, green: 0.964, blue: 0.976))
        .alert("已复制 QQ 号：\(AppConfig.contactQQ)", isPresented: $showCopied) {
            Button("好", role: .cancel) {}
        }
    }
}

struct PillButtonStyle: ButtonStyle {
    var background: Color
    var foreground: Color
    var border: Color

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.subheadline.weight(.semibold))
            .foregroundColor(foreground)
            .frame(maxWidth: .infinity)
            .frame(height: 46)
            .background(background)
            .overlay(
                RoundedRectangle(cornerRadius: 10)
                    .stroke(border, lineWidth: border == .clear ? 0 : 1)
            )
            .clipShape(RoundedRectangle(cornerRadius: 10))
            .opacity(configuration.isPressed ? 0.85 : 1)
    }
}
