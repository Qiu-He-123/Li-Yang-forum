import Foundation

/// 微云公告拉取：解析 window.syncData 里的笔记正文（与安卓版同逻辑）
enum WeiyunNotice {
    static func fetch(completion: @escaping (String?) -> Void) {
        var request = URLRequest(url: AppConfig.noticeUrl)
        request.timeoutInterval = 15
        request.setValue(
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                + "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
            forHTTPHeaderField: "User-Agent"
        )
        URLSession.shared.dataTask(with: request) { data, _, _ in
            guard let data = data, let html = String(data: data, encoding: .utf8) else {
                completion(nil)
                return
            }
            completion(parse(html))
        }.resume()
    }

    static func parse(_ html: String) -> String? {
        guard let marker = html.range(of: "window.syncData = "),
              let open = html[marker.upperBound...].range(of: "{"),
              let scriptEnd = html[open.upperBound...].range(of: "</script>")
        else { return nil }

        let jsonSlice = html[open.lowerBound..<scriptEnd.lowerBound]
        guard let lastBrace = jsonSlice.lastIndex(of: "}") else { return nil }
        let jsonText = String(jsonSlice[..<jsonSlice.index(after: lastBrace)])

        guard let data = jsonText.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { return nil }

        let share = (obj["shareInfo"] as? [String: Any]) ?? obj
        guard let notes = share["note_list"] as? [[String: Any]],
              let note = notes.first
        else { return nil }

        let content = (note["html_content"] as? String)
            ?? (note["note_title"] as? String)
            ?? (share["share_name"] as? String)
        guard let content else { return nil }

        return parseFields(content)
    }

    /// 去掉 HTML 标签，逐行保留「标签{内容}」原文（与安卓 parseFields 一致）
    static func parseFields(_ htmlContent: String) -> String? {
        let text = htmlContent.replacingOccurrences(
            of: "<[^>]+>",
            with: "\n",
            options: .regularExpression
        )
        let lines = text
            .split(separator: "\n")
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
        let result = lines.joined(separator: "\n")
        return result.isEmpty ? nil : result
    }
}
