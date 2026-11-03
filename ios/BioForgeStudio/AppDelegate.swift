import UIKit
import WebKit

@main
final class AppDelegate: UIResponder, UIApplicationDelegate {
    var window: UIWindow?

    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
    ) -> Bool {
        let window = UIWindow(frame: UIScreen.main.bounds)
        window.rootViewController = BioForgeViewController()
        window.makeKeyAndVisible()
        self.window = window
        return true
    }
}

private final class WeakScriptMessageHandler: NSObject, WKScriptMessageHandler {
    weak var delegate: WKScriptMessageHandler?

    init(delegate: WKScriptMessageHandler) {
        self.delegate = delegate
    }

    func userContentController(
        _ userContentController: WKUserContentController,
        didReceive message: WKScriptMessage
    ) {
        delegate?.userContentController(userContentController, didReceive: message)
    }
}

final class BioForgeViewController: UIViewController {
    private static let serverKey = "server_url"
    private static let bridgeName = "bioforge"
    private static let backgroundColor = UIColor(
        red: 245.0 / 255.0,
        green: 245.0 / 255.0,
        blue: 247.0 / 255.0,
        alpha: 1.0
    )

    private var webView: WKWebView!
    private var savedServer = ""
    private var offlinePreview = false
    private var isProbing = false
    private var isServerDialogVisible = false
    private var toastLabel: UILabel?
    private var pendingExportURL: URL?
    private var hasStarted = false
    private var lastExternalOpen: (url: URL, date: Date)?

    override var preferredStatusBarStyle: UIStatusBarStyle {
        .darkContent
    }

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = Self.backgroundColor
        configureWebView()
    }

    override func viewDidAppear(_ animated: Bool) {
        super.viewDidAppear(animated)
        guard !hasStarted else { return }
        hasStarted = true
        loadSavedServer()
    }

    deinit {
        webView?.configuration.userContentController.removeScriptMessageHandler(forName: Self.bridgeName)
    }

    private func configureWebView() {
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .default()
        configuration.defaultWebpagePreferences.allowsContentJavaScript = true
        configuration.preferences.javaScriptCanOpenWindowsAutomatically = true
        configuration.allowsInlineMediaPlayback = true
        configuration.mediaTypesRequiringUserActionForPlayback = []
        configuration.userContentController.add(
            WeakScriptMessageHandler(delegate: self),
            name: Self.bridgeName
        )

        webView = WKWebView(frame: .zero, configuration: configuration)
        webView.translatesAutoresizingMaskIntoConstraints = false
        webView.navigationDelegate = self
        webView.uiDelegate = self
        webView.allowsBackForwardNavigationGestures = true
        webView.scrollView.contentInsetAdjustmentBehavior = .automatic
        webView.isOpaque = false
        webView.backgroundColor = Self.backgroundColor
        webView.scrollView.backgroundColor = Self.backgroundColor
        if #available(iOS 15.0, *) {
            webView.underPageBackgroundColor = Self.backgroundColor
        }

        view.addSubview(webView)
        NSLayoutConstraint.activate([
            webView.leadingAnchor.constraint(equalTo: view.leadingAnchor),
            webView.trailingAnchor.constraint(equalTo: view.trailingAnchor),
            webView.topAnchor.constraint(equalTo: view.topAnchor),
            webView.bottomAnchor.constraint(equalTo: view.bottomAnchor)
        ])
    }

    private func loadSavedServer() {
        savedServer = UserDefaults.standard.string(forKey: Self.serverKey) ?? ""
        if savedServer.isEmpty {
            showServerDialog(firstRun: true)
            return
        }
        loadRemote(server: savedServer)
    }

    private func loadRemote(server: String) {
        guard let url = URL(string: server) else {
            showServerDialog(firstRun: false, error: "服务器地址格式无效。")
            return
        }
        offlinePreview = false
        installBridge(server: server)
        webView.load(URLRequest(url: url, cachePolicy: .useProtocolCachePolicy, timeoutInterval: 30))
    }

    private func loadOfflinePreview() {
        offlinePreview = true
        installBridge(server: savedServer)
        guard let index = bundledIndexURL() else {
            showToast("离线资源缺失，请重新安装 App。")
            return
        }
        webView.loadFileURL(index, allowingReadAccessTo: index.deletingLastPathComponent())
        showToast("离线预览模式：服务器功能与登录不可用")
    }

    private func bundledIndexURL() -> URL? {
        if let url = Bundle.main.url(forResource: "index", withExtension: "html", subdirectory: "www") {
            return url
        }
        if let directory = Bundle.main.url(forResource: "www", withExtension: nil) {
            return directory.appendingPathComponent("index.html")
        }
        return nil
    }

    private func installBridge(server: String) {
        let controller = webView.configuration.userContentController
        controller.removeAllUserScripts()
        controller.addUserScript(
            WKUserScript(
                source: bridgeScript(server: server),
                injectionTime: .atDocumentStart,
                forMainFrameOnly: true
            )
        )
    }

    private func bridgeScript(server: String) -> String {
        let serverLiteral = Self.jsonString(server)
        return """
        (function () {
          if (window.AndroidBridge) { return; }
          window.__bioforgeServerUrl = \(serverLiteral);
          window.AndroidBridge = {
            saveText: function (filename, mime, content) {
              window.webkit.messageHandlers.bioforge.postMessage({
                action: "saveText",
                filename: String(filename || "bioforge-export.txt"),
                mime: String(mime || "text/plain"),
                content: String(content || "")
              });
            },
            openServerSettings: function () {
              window.webkit.messageHandlers.bioforge.postMessage({ action: "openServerSettings" });
            },
            getServerUrl: function () {
              return window.__bioforgeServerUrl || "";
            },
            toast: function (message) {
              window.webkit.messageHandlers.bioforge.postMessage({
                action: "toast",
                message: String(message || "")
              });
            }
          };
        })();
        """
    }

    private static func jsonString(_ value: String) -> String {
        let data = (try? JSONSerialization.data(withJSONObject: [value], options: [])) ?? Data("[\"\"]".utf8)
        let array = String(data: data, encoding: .utf8) ?? "[\"\"]"
        return String(array.dropFirst().dropLast())
    }

    private func defaultServer() -> String {
        #if targetEnvironment(simulator)
        return "http://127.0.0.1:8010/"
        #else
        return ""
        #endif
    }

    private func normalizeServer(_ raw: String?) -> String? {
        var value = (raw ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        guard !value.isEmpty else { return nil }
        let lower = value.lowercased()
        if !lower.hasPrefix("http://") && !lower.hasPrefix("https://") {
            value = "http://" + value
        }
        while value.hasSuffix("/") {
            value.removeLast()
        }
        guard let components = URLComponents(string: value),
              let scheme = components.scheme?.lowercased(),
              scheme == "http" || scheme == "https",
              let host = components.host,
              !host.isEmpty else {
            return nil
        }
        return value + "/"
    }

    private func connectToServer(_ raw: String, firstRun: Bool) {
        guard !isProbing else { return }
        guard let server = normalizeServer(raw) else {
            showServerDialog(
                firstRun: firstRun,
                error: "请输入完整地址，例如 http://192.168.1.23:8010/"
            )
            return
        }
        isProbing = true
        showToast("正在连接 \(server) …")
        probeServer(server) { [weak self] error in
            guard let self else { return }
            self.isProbing = false
            if let error {
                self.showServerDialog(firstRun: firstRun, error: error)
                return
            }
            self.savedServer = server
            UserDefaults.standard.set(server, forKey: Self.serverKey)
            self.loadRemote(server: server)
        }
    }

    private func probeServer(_ server: String, completion: @escaping (String?) -> Void) {
        guard let url = URL(string: server + "api/health") else {
            completion("服务器地址格式无效。")
            return
        }
        var request = URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 7)
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        URLSession.shared.dataTask(with: request) { data, response, error in
            let result: String?
            if let error {
                result = "无法连接：\(error.localizedDescription)"
            } else if let http = response as? HTTPURLResponse,
                      !(200...299).contains(http.statusCode) {
                result = "服务器返回 HTTP \(http.statusCode)。请检查端口和地址。"
            } else if let data,
                      let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                      object["status"] != nil,
                      object["version"] != nil {
                result = nil
            } else {
                result = "该地址不是 BioForge 服务器。"
            }
            DispatchQueue.main.async {
                completion(result)
            }
        }.resume()
    }

    private func showServerDialog(firstRun: Bool, error: String? = nil) {
        guard !isServerDialogVisible, presentedViewController == nil else { return }
        isServerDialogVisible = true

        var message = """
        输入运行 BioForge 服务器的电脑地址。iPhone/iPad 与电脑需在同一 Wi-Fi；服务器默认监听 0.0.0.0:8010。

        示例：http://192.168.1.23:8010/
        """
        if let error, !error.isEmpty {
            message += "\n\n" + error
        }

        let alert = UIAlertController(
            title: "连接 BioForge 服务器",
            message: message,
            preferredStyle: .alert
        )
        alert.addTextField { [weak self] field in
            guard let self else { return }
            field.placeholder = "http://192.168.1.23:8010/"
            field.text = self.savedServer.isEmpty ? self.defaultServer() : self.savedServer
            field.keyboardType = .URL
            field.autocapitalizationType = .none
            field.autocorrectionType = .no
            field.clearButtonMode = .whileEditing
        }
        alert.addAction(UIAlertAction(title: "离线预览", style: .default) { [weak self] _ in
            self?.isServerDialogVisible = false
            self?.loadOfflinePreview()
        })
        alert.addAction(UIAlertAction(title: "连接并保存", style: .default) { [weak self, weak alert] _ in
            guard let self else { return }
            self.isServerDialogVisible = false
            let raw = alert?.textFields?.first?.text ?? ""
            self.connectToServer(raw, firstRun: firstRun)
        })
        if !firstRun {
            alert.addAction(UIAlertAction(title: "取消", style: .cancel) { [weak self] _ in
                self?.isServerDialogVisible = false
            })
        }
        present(alert, animated: true)
    }

    private func saveText(filename: String?, mime: String?, content: String?) {
        _ = mime
        guard presentedViewController == nil else {
            showToast("请先关闭当前对话框。")
            return
        }
        let name = sanitizeFilename(filename)
        let data = (content ?? "").data(using: .utf8) ?? Data()
        let url = FileManager.default.temporaryDirectory.appendingPathComponent(name)
        do {
            try data.write(to: url, options: .atomic)
        } catch {
            showToast("保存失败：\(error.localizedDescription)")
            return
        }
        if let previous = pendingExportURL, previous != url {
            try? FileManager.default.removeItem(at: previous)
        }
        pendingExportURL = url
        let picker = UIDocumentPickerViewController(forExporting: [url], asCopy: true)
        picker.delegate = self
        present(picker, animated: true)
    }

    private func sanitizeFilename(_ filename: String?) -> String {
        let raw = (filename ?? "bioforge-export.txt").trimmingCharacters(in: .whitespacesAndNewlines)
        let invalid = CharacterSet(charactersIn: "\\/:*?\"<>|")
        var name = raw.components(separatedBy: invalid).joined(separator: "_")
        if name.isEmpty {
            name = "bioforge-export.txt"
        }
        if name.count > 140 {
            name = String(name.suffix(140))
        }
        return name
    }

    private func cleanupExport() {
        if let url = pendingExportURL {
            try? FileManager.default.removeItem(at: url)
        }
        pendingExportURL = nil
    }

    private func isCancellation(_ error: Error) -> Bool {
        let nsError = error as NSError
        return nsError.domain == NSURLErrorDomain && nsError.code == NSURLErrorCancelled
    }

    private func openExternal(_ url: URL) {
        if let last = lastExternalOpen,
           last.url == url,
           Date().timeIntervalSince(last.date) < 1.0 {
            return
        }
        lastExternalOpen = (url, Date())
        guard UIApplication.shared.canOpenURL(url) else {
            showToast("无法打开外部链接。")
            return
        }
        UIApplication.shared.open(url, options: [:], completionHandler: nil)
    }

    private func showToast(_ text: String) {
        guard !text.isEmpty else { return }
        toastLabel?.removeFromSuperview()

        let label = UILabel()
        label.translatesAutoresizingMaskIntoConstraints = false
        label.text = "  \(text)  "
        label.numberOfLines = 0
        label.textAlignment = .center
        label.textColor = .white
        label.font = .systemFont(ofSize: 14, weight: .medium)
        label.backgroundColor = UIColor.black.withAlphaComponent(0.78)
        label.layer.cornerRadius = 12
        label.layer.masksToBounds = true
        label.alpha = 0
        view.addSubview(label)
        NSLayoutConstraint.activate([
            label.centerXAnchor.constraint(equalTo: view.centerXAnchor),
            label.bottomAnchor.constraint(equalTo: view.safeAreaLayoutGuide.bottomAnchor, constant: -24),
            label.leadingAnchor.constraint(greaterThanOrEqualTo: view.leadingAnchor, constant: 24),
            label.trailingAnchor.constraint(lessThanOrEqualTo: view.trailingAnchor, constant: -24)
        ])
        toastLabel = label

        UIView.animate(withDuration: 0.2, animations: {
            label.alpha = 1
        }) { _ in
            DispatchQueue.main.asyncAfter(deadline: .now() + 2.6) { [weak self, weak label] in
                guard let label else { return }
                UIView.animate(withDuration: 0.25, animations: {
                    label.alpha = 0
                }) { _ in
                    label.removeFromSuperview()
                    if self?.toastLabel === label {
                        self?.toastLabel = nil
                    }
                }
            }
        }
    }
}

extension BioForgeViewController: WKScriptMessageHandler {
    func userContentController(
        _ userContentController: WKUserContentController,
        didReceive message: WKScriptMessage
    ) {
        guard message.name == Self.bridgeName,
              let body = message.body as? [String: Any],
              let action = body["action"] as? String else {
            return
        }
        switch action {
        case "saveText":
            saveText(
                filename: body["filename"] as? String,
                mime: body["mime"] as? String,
                content: body["content"] as? String
            )
        case "openServerSettings":
            showServerDialog(firstRun: false)
        case "toast":
            showToast(body["message"] as? String ?? "")
        default:
            break
        }
    }
}

extension BioForgeViewController: WKNavigationDelegate {
    func webView(
        _ webView: WKWebView,
        decidePolicyFor navigationAction: WKNavigationAction,
        decisionHandler: @escaping (WKNavigationActionPolicy) -> Void
    ) {
        guard let url = navigationAction.request.url else {
            decisionHandler(.allow)
            return
        }
        let scheme = url.scheme?.lowercased() ?? ""
        if scheme == "file" {
            decisionHandler(.allow)
            return
        }
        if scheme == "http" || scheme == "https" {
            guard let target = navigationAction.targetFrame, target.isMainFrame else {
                decisionHandler(.allow)
                return
            }
            let host = url.host?.lowercased() ?? ""
            let savedHost = URL(string: savedServer)?.host?.lowercased() ?? ""
            if !savedHost.isEmpty && host != savedHost {
                openExternal(url)
                decisionHandler(.cancel)
                return
            }
            decisionHandler(.allow)
            return
        }
        if scheme == "mailto" || scheme == "tel" {
            openExternal(url)
            decisionHandler(.cancel)
            return
        }
        decisionHandler(.cancel)
    }

    func webView(
        _ webView: WKWebView,
        decidePolicyFor navigationResponse: WKNavigationResponse,
        decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void
    ) {
        if navigationResponse.isForMainFrame,
           !offlinePreview,
           let http = navigationResponse.response as? HTTPURLResponse,
           http.statusCode >= 500 {
            DispatchQueue.main.async { [weak self] in
                self?.showServerDialog(
                    firstRun: false,
                    error: "服务器返回 HTTP \(http.statusCode)。"
                )
            }
        }
        decisionHandler(.allow)
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        if let scheme = webView.url?.scheme?.lowercased(), scheme == "http" || scheme == "https" {
            offlinePreview = false
        }
    }

    func webView(
        _ webView: WKWebView,
        didFailProvisionalNavigation navigation: WKNavigation!,
        withError error: Error
    ) {
        guard !offlinePreview, !isCancellation(error) else { return }
        showServerDialog(firstRun: false, error: "无法连接：\(error.localizedDescription)")
    }

    func webView(
        _ webView: WKWebView,
        didFail navigation: WKNavigation!,
        withError error: Error
    ) {
        guard !offlinePreview, !isCancellation(error) else { return }
        showServerDialog(firstRun: false, error: "无法连接：\(error.localizedDescription)")
    }

    func webViewWebContentProcessDidTerminate(_ webView: WKWebView) {
        if offlinePreview {
            loadOfflinePreview()
        } else {
            webView.reload()
        }
    }
}

extension BioForgeViewController: WKUIDelegate {
    func webView(
        _ webView: WKWebView,
        createWebViewWith configuration: WKWebViewConfiguration,
        for navigationAction: WKNavigationAction,
        windowFeatures: WKWindowFeatures
    ) -> WKWebView? {
        if let url = navigationAction.request.url {
            openExternal(url)
        }
        return nil
    }
}

extension BioForgeViewController: UIDocumentPickerDelegate {
    func documentPicker(
        _ controller: UIDocumentPickerViewController,
        didPickDocumentsAt urls: [URL]
    ) {
        cleanupExport()
    }

    func documentPickerWasCancelled(_ controller: UIDocumentPickerViewController) {
        cleanupExport()
    }
}
