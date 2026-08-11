import Foundation

/// 和安卓版保持一致的配置常量（安卓在 MainActivity 顶部常量里）
enum AppConfig {
    static let appUrl = URL(string: "https://al.u3593529.nyat.app:32449")!
    static let noticeUrl = URL(string: "https://share.weiyun.com/SpmKBnmC")!
    static let contactQQ = "qhqe2623655749"
    static let defaultNotice = "请检查网络连接是否正常以及联系管理员"
    /// 自定义 UA 标记：网页端据此隐藏「下载手机端」按钮、后台据此统计手机端进入
    static let userAgentSuffix = " LYCommunityApp/1.0"
}
