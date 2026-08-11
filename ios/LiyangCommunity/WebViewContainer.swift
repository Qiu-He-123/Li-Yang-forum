import SwiftUI
import WebKit
import PhotosUI
import UniformTypeIdentifiers

/// 网页容器：WKWebView 套壳，行为与安卓版一致
/// - 自定义 UA（LYCommunityApp）→ 网页端隐藏下载按钮、后台统计手机端进入
/// - Cookie 由 WKWebsiteDataStore 自动持久化，重开 App 保持登录
/// - 左边缘右滑 = 返回上一页；网页上传图片走系统相册选择
struct WebViewContainer: UIViewRepresentable {
    @Binding var showOffline: Bool
    @Binding var pageLoaded: Bool
    @Binding var reloadTrigger: Int

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    func makeUIView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        config.websiteDataStore = .default()
        let webView = WKWebView(frame: .zero, configuration: config)
        webView.navigationDelegate = context.coordinator
        webView.uiDelegate = context.coordinator
        webView.allowsBackForwardNavigationGestures = true

        let defaultUA = (webView.value(forKey: "userAgent") as? String) ?? ""
        webView.customUserAgent = defaultUA + AppConfig.userAgentSuffix

        let edgePan = UIScreenEdgePanGestureRecognizer(
            target: context.coordinator,
            action: #selector(Coordinator.handleEdgePan(_:))
        )
        edgePan.edges = .left
        webView.addGestureRecognizer(edgePan)

        webView.load(URLRequest(url: AppConfig.appUrl))
        return webView
    }

    func updateUIView(_ uiView: WKWebView, context: Context) {
        // 「重新连接」触发刷新
        if reloadTrigger != context.coordinator.lastReloadTrigger {
            context.coordinator.lastReloadTrigger = reloadTrigger
            uiView.reload()
        }
    }

    final class Coordinator: NSObject, WKNavigationDelegate, WKUIDelegate {
        var parent: WebViewContainer
        var lastReloadTrigger = 0
        private var filePickerDelegate: ImagePickerDelegate?

        init(_ parent: WebViewContainer) {
            self.parent = parent
        }

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            parent.pageLoaded = true
        }

        func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
            parent.showOffline = true
        }

        func webView(
            _ webView: WKWebView,
            didFailProvisionalNavigation navigation: WKNavigation!,
            withError error: Error
        ) {
            parent.showOffline = true
        }

        func webView(
            _ webView: WKWebView,
            decidePolicyFor navigationResponse: WKNavigationResponse,
            decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void
        ) {
            if let http = navigationResponse.response as? HTTPURLResponse, http.statusCode >= 500 {
                parent.showOffline = true
            }
            decisionHandler(.allow)
        }

        @objc func handleEdgePan(_ gesture: UIScreenEdgePanGestureRecognizer) {
            guard gesture.state == .ended,
                  let webView = gesture.view as? WKWebView,
                  webView.canGoBack else { return }
            webView.goBack()
        }

        // 网页里的图片/文件选择（对应安卓的 onShowFileChooser）
        func webView(
            _ webView: WKWebView,
            runOpenPanelWith parameters: WKOpenPanelParameters,
            initiatedByFrame frame: WKFrameInfo,
            completionHandler: @escaping ([URL]?) -> Void
        ) {
            var config = PHPickerConfiguration()
            config.selectionLimit = 1
            config.filter = .images
            let picker = PHPickerViewController(configuration: config)
            let delegate = ImagePickerDelegate(completion: completionHandler)
            filePickerDelegate = delegate
            picker.delegate = delegate
            topViewController()?.present(picker, animated: true)
        }

        private func topViewController() -> UIViewController? {
            guard let scene = UIApplication.shared.connectedScenes.first as? UIWindowScene,
                  let root = scene.windows.first(where: { $0.isKeyWindow })?.rootViewController
            else { return nil }
            var top = root
            while let presented = top.presentedViewController {
                top = presented
            }
            return top
        }
    }
}

final class ImagePickerDelegate: NSObject, PHPickerViewControllerDelegate {
    private let completion: ([URL]?) -> Void

    init(completion: @escaping ([URL]?) -> Void) {
        self.completion = completion
        super.init()
    }

    func picker(_ picker: PHPickerViewController, didFinishPicking results: [PHPickerResult]) {
        picker.dismiss(animated: true)
        guard let provider = results.first?.itemProvider else {
            completion(nil)
            return
        }
        let type = UTType.image.identifier
        guard provider.hasItemConformingToTypeIdentifier(type) else {
            completion(nil)
            return
        }
        provider.loadFileRepresentation(forTypeIdentifier: type) { [weak self] url, _ in
            DispatchQueue.main.async {
                self?.completion(url.map { [$0] })
            }
        }
    }
}
