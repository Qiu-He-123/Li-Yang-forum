import SwiftUI

struct ContentView: View {
    @State private var showOffline = false
    @State private var pageLoaded = false
    @State private var splashHidden = false
    @State private var reloadTrigger = 0
    @State private var noticeText = AppConfig.defaultNotice

    var body: some View {
        ZStack {
            WebViewContainer(
                showOffline: $showOffline,
                pageLoaded: $pageLoaded,
                reloadTrigger: $reloadTrigger
            )
            .ignoresSafeArea()

            if showOffline {
                OfflineView(
                    noticeText: $noticeText,
                    onRetry: {
                        showOffline = false
                        reloadTrigger += 1
                    },
                    onContact: {
                        UIPasteboard.general.string = AppConfig.contactQQ
                    }
                )
                .transition(.opacity)
            }

            if !splashHidden {
                SplashView()
                    .transition(.opacity)
                    .zIndex(10)
            }
        }
        .onChange(of: pageLoaded) { loaded in
            guard loaded, !splashHidden else { return }
            // 启动页至少展示 1.2 秒，避免一闪而过（与安卓一致）
            DispatchQueue.main.asyncAfter(deadline: .now() + 1.2) {
                withAnimation(.easeOut(duration: 0.35)) {
                    splashHidden = true
                }
            }
        }
        .task {
            // 打开 App 先拉取微云笔记公告（服务器挂了时维护页直接显示）
            WeiyunNotice.fetch { text in
                DispatchQueue.main.async {
                    if let text = text, !text.isEmpty {
                        noticeText = text
                    }
                }
            }
        }
    }
}
