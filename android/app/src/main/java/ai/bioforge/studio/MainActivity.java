package ai.bioforge.studio;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.text.InputType;
import android.view.View;
import android.view.ViewGroup;
import android.webkit.JavascriptInterface;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

public class MainActivity extends Activity {
    private static final int REQ_SAVE = 1001;
    private static final int REQ_FILE = 1002;
    private static final String PREFS = "bioforge";
    private static final String SERVER_KEY = "server_url";

    private ValueCallback<Uri[]> filePathCallback;
    private WebView webView;
    private AlertDialog serverDialog;
    private EditText serverInput;
    private TextView serverStatus;
    private Button connectButton;
    private String pendingName = "bioforge-export.txt";
    private String pendingMime = "text/plain";
    private String pendingContent = "";
    private boolean offlinePreview = false;
    private boolean serverDialogRequired = false;

    private String savedServer() {
        return getSharedPreferences(PREFS, MODE_PRIVATE).getString(SERVER_KEY, "");
    }

    private String defaultServer() {
        boolean emulator = Build.FINGERPRINT.contains("generic")
                || Build.MODEL.contains("sdk")
                || Build.MODEL.contains("Emulator");
        return emulator ? "http://10.0.2.2:8010/" : "";
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    private String normalizeServer(String raw) {
        String value = raw == null ? "" : raw.trim();
        if (value.isEmpty()) {
            return "";
        }
        if (!value.startsWith("http://") && !value.startsWith("https://")) {
            value = "http://" + value;
        }
        while (value.endsWith("/")) {
            value = value.substring(0, value.length() - 1);
        }
        Uri uri = Uri.parse(value);
        String scheme = uri.getScheme();
        if (!"http".equals(scheme) && !"https".equals(scheme)) {
            return "";
        }
        if (uri.getHost() == null || uri.getHost().isEmpty()) {
            return "";
        }
        return value + "/";
    }

    private String probeServer(String server) {
        HttpURLConnection connection = null;
        try {
            connection = (HttpURLConnection) new URL(server + "api/health").openConnection();
            connection.setConnectTimeout(7000);
            connection.setReadTimeout(7000);
            connection.setInstanceFollowRedirects(true);
            connection.setRequestProperty("Accept", "application/json");
            connection.setRequestMethod("GET");
            int code = connection.getResponseCode();
            if (code < 200 || code >= 300) {
                return "服务器返回 HTTP " + code + "。请检查端口和地址。";
            }
            StringBuilder body = new StringBuilder();
            try (InputStream input = connection.getInputStream();
                 BufferedReader reader = new BufferedReader(new InputStreamReader(input, StandardCharsets.UTF_8))) {
                String line;
                while ((line = reader.readLine()) != null && body.length() < 4096) {
                    body.append(line);
                }
            }
            String text = body.toString();
            if (!text.contains("\"status\"") || !text.contains("\"version\"")) {
                return "该地址不是 BioForge 服务器。";
            }
            return null;
        } catch (Exception exc) {
            return "无法连接：" + (exc.getMessage() == null ? exc.getClass().getSimpleName() : exc.getMessage());
        } finally {
            if (connection != null) {
                connection.disconnect();
            }
        }
    }

    private void connectToServer(String raw) {
        final String server = normalizeServer(raw);
        if (server.isEmpty()) {
            serverStatus.setText("请输入完整地址，例如 http://192.168.1.23:8010/");
            serverStatus.setTextColor(Color.parseColor("#B42318"));
            return;
        }
        connectButton.setEnabled(false);
        serverStatus.setText("正在连接 " + server + " …");
        serverStatus.setTextColor(Color.parseColor("#5B6472"));
        new Thread(() -> {
            final String error = probeServer(server);
            runOnUiThread(() -> {
                connectButton.setEnabled(true);
                if (error == null) {
                    getSharedPreferences(PREFS, MODE_PRIVATE).edit().putString(SERVER_KEY, server).apply();
                    offlinePreview = false;
                    if (serverDialog != null) {
                        serverDialog.dismiss();
                    }
                    webView.getSettings().setCacheMode(WebSettings.LOAD_DEFAULT);
                    webView.loadUrl(server);
                } else {
                    serverStatus.setText(error);
                    serverStatus.setTextColor(Color.parseColor("#B42318"));
                }
            });
        }).start();
    }

    private void loadOfflinePreview() {
        offlinePreview = true;
        if (serverDialog != null) {
            serverDialog.dismiss();
        }
        WebSettings settings = webView.getSettings();
        settings.setCacheMode(WebSettings.LOAD_CACHE_ELSE_NETWORK);
        webView.loadUrl("file:///android_asset/www/index.html");
        Toast.makeText(this, "离线预览模式：服务器功能与登录不可用", Toast.LENGTH_LONG).show();
    }

    private void showServerDialog(final boolean firstRun) {
        if (isFinishing()) {
            return;
        }
        if (serverDialog != null && serverDialog.isShowing()) {
            serverDialog.dismiss();
        }
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        int pad = dp(22);
        box.setPadding(pad, dp(8), pad, dp(4));

        TextView help = new TextView(this);
        help.setText("输入运行 BioForge 服务器的电脑地址。手机与电脑需在同一 Wi-Fi；服务器默认监听 0.0.0.0:8010。\n\n示例：http://192.168.1.23:8010/");
        help.setTextSize(14);
        help.setTextColor(Color.parseColor("#3C4350"));
        help.setLineSpacing(dp(2), 1.0f);
        box.addView(help, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));

        serverInput = new EditText(this);
        serverInput.setSingleLine(true);
        serverInput.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        serverInput.setHint("http://192.168.1.23:8010/");
        String current = savedServer();
        serverInput.setText(current.isEmpty() ? defaultServer() : current);
        serverInput.setSelectAllOnFocus(false);
        LinearLayout.LayoutParams inputParams = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        inputParams.topMargin = dp(16);
        box.addView(serverInput, inputParams);

        serverStatus = new TextView(this);
        serverStatus.setTextSize(13);
        serverStatus.setTextColor(Color.parseColor("#5B6472"));
        serverStatus.setPadding(0, dp(10), 0, dp(4));
        box.addView(serverStatus, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));

        LinearLayout actions = new LinearLayout(this);
        actions.setOrientation(LinearLayout.HORIZONTAL);
        actions.setPadding(0, dp(10), 0, 0);

        Button offlineButton = new Button(this);
        offlineButton.setText("离线预览");
        offlineButton.setAllCaps(false);
        offlineButton.setOnClickListener(v -> loadOfflinePreview());
        actions.addView(offlineButton, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));

        connectButton = new Button(this);
        connectButton.setText("连接并保存");
        connectButton.setAllCaps(false);
        connectButton.setOnClickListener(v -> connectToServer(serverInput.getText().toString()));
        LinearLayout.LayoutParams connectParams = new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1.35f);
        connectParams.leftMargin = dp(8);
        actions.addView(connectButton, connectParams);
        box.addView(actions, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));

        ScrollView scroll = new ScrollView(this);
        scroll.addView(box);

        AlertDialog.Builder builder = new AlertDialog.Builder(this)
                .setTitle("连接 BioForge 服务器")
                .setView(scroll)
                .setCancelable(!firstRun);
        if (!firstRun) {
            builder.setNegativeButton("取消", (dialog, which) -> dialog.dismiss());
        }
        serverDialog = builder.create();
        serverDialogRequired = firstRun;
        serverDialog.setOnDismissListener(dialog -> {
            serverDialogRequired = false;
            serverInput = null;
            serverStatus = null;
            connectButton = null;
        });
        serverDialog.show();
    }

    private void loadSavedServer() {
        String saved = savedServer();
        if (saved.isEmpty()) {
            showServerDialog(true);
            return;
        }
        webView.getSettings().setCacheMode(WebSettings.LOAD_DEFAULT);
        webView.loadUrl(saved);
    }

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getWindow().setStatusBarColor(Color.parseColor("#F5F5F7"));
        getWindow().setNavigationBarColor(Color.parseColor("#F5F5F7"));
        if (Build.VERSION.SDK_INT >= 23) {
            getWindow().getDecorView().setSystemUiVisibility(
                    View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR
                            | View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR);
        }

        webView = new WebView(this);
        webView.setBackgroundColor(Color.parseColor("#F5F5F7"));
        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setDatabaseEnabled(true);
        settings.setAllowFileAccess(true);
        settings.setAllowContentAccess(true);
        settings.setAllowFileAccessFromFileURLs(false);
        settings.setAllowUniversalAccessFromFileURLs(false);
        settings.setMediaPlaybackRequiresUserGesture(false);
        settings.setCacheMode(WebSettings.LOAD_DEFAULT);

        webView.addJavascriptInterface(new Bridge(), "AndroidBridge");
        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
                if (filePathCallback != null) {
                    filePathCallback.onReceiveValue(null);
                }
                filePathCallback = callback;
                try {
                    startActivityForResult(params.createIntent(), REQ_FILE);
                    return true;
                } catch (Exception exc) {
                    filePathCallback = null;
                    callback.onReceiveValue(null);
                    Toast.makeText(MainActivity.this, "无法打开文件选择器", Toast.LENGTH_SHORT).show();
                    return false;
                }
            }
        });
        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri uri = request.getUrl();
                String scheme = uri.getScheme() == null ? "" : uri.getScheme();
                if ("file".equals(scheme)) {
                    return false;
                }
                String host = uri.getHost() == null ? "" : uri.getHost();
                String currentHost = Uri.parse(savedServer()).getHost();
                if (("http".equals(scheme) || "https".equals(scheme)) && host.equals(currentHost)) {
                    return false;
                }
                if ("http".equals(scheme) || "https".equals(scheme)) {
                    try {
                        startActivity(new Intent(Intent.ACTION_VIEW, uri));
                    } catch (Exception ignored) {
                        Toast.makeText(MainActivity.this, "无法打开外部链接", Toast.LENGTH_SHORT).show();
                    }
                    return true;
                }
                return true;
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame() && !offlinePreview) {
                    String failed = request.getUrl().toString();
                    if (failed.startsWith("http://") || failed.startsWith("https://")) {
                        showServerDialog(false);
                    }
                }
            }

            @Override
            public void onReceivedHttpError(WebView view, WebResourceRequest request, WebResourceResponse response) {
                if (request.isForMainFrame() && !offlinePreview && response.getStatusCode() >= 500) {
                    showServerDialog(false);
                }
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                if (url != null && (url.startsWith("http://") || url.startsWith("https://"))) {
                    offlinePreview = false;
                }
            }
        });

        setContentView(webView);
        loadSavedServer();
    }

    private class Bridge {
        @JavascriptInterface
        public void saveText(String filename, String mime, String content) {
            String name = filename == null ? "bioforge-export.txt" : filename.replaceAll("[\\\\/:*?\"<>|]", "_");
            if (name.length() > 140) {
                name = name.substring(name.length() - 140);
            }
            String type = mime == null ? "text/plain" : mime;
            if (!(type.startsWith("text/") || "application/json".equals(type))) {
                type = "text/plain";
            }
            pendingName = name;
            pendingMime = type;
            pendingContent = content == null ? "" : content;
            runOnUiThread(() -> {
                try {
                    Intent intent = new Intent(Intent.ACTION_CREATE_DOCUMENT);
                    intent.addCategory(Intent.CATEGORY_OPENABLE);
                    intent.setType(pendingMime);
                    intent.putExtra(Intent.EXTRA_TITLE, pendingName);
                    startActivityForResult(intent, REQ_SAVE);
                } catch (Exception exc) {
                    Toast.makeText(MainActivity.this, "无法打开保存对话框", Toast.LENGTH_SHORT).show();
                }
            });
        }

        @JavascriptInterface
        public void openServerSettings() {
            runOnUiThread(() -> showServerDialog(false));
        }

        @JavascriptInterface
        public String getServerUrl() {
            return savedServer();
        }

        @JavascriptInterface
        public void toast(String message) {
            runOnUiThread(() -> Toast.makeText(MainActivity.this, message == null ? "" : message, Toast.LENGTH_SHORT).show());
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == REQ_FILE) {
            if (filePathCallback != null) {
                Uri uri = resultCode == RESULT_OK && data != null ? data.getData() : null;
                filePathCallback.onReceiveValue(uri == null ? null : new Uri[]{uri});
                filePathCallback = null;
            }
            return;
        }
        if (requestCode == REQ_SAVE && resultCode == RESULT_OK && data != null && data.getData() != null) {
            try (OutputStream out = getContentResolver().openOutputStream(data.getData())) {
                if (out != null) {
                    out.write(pendingContent.getBytes(StandardCharsets.UTF_8));
                    out.flush();
                    Toast.makeText(this, "已保存 " + pendingName, Toast.LENGTH_SHORT).show();
                }
            } catch (Exception exc) {
                Toast.makeText(this, "保存失败：" + exc.getMessage(), Toast.LENGTH_SHORT).show();
            } finally {
                pendingContent = "";
            }
        }
    }

    @Override
    @SuppressWarnings("deprecation")
    public void onBackPressed() {
        if (serverDialog != null && serverDialog.isShowing()) {
            if (!serverDialogRequired) {
                serverDialog.dismiss();
            }
            return;
        }
        if (webView != null && webView.canGoBack()) {
            webView.goBack();
        } else {
            super.onBackPressed();
        }
    }

    @Override
    protected void onDestroy() {
        if (serverDialog != null) {
            serverDialog.dismiss();
        }
        if (webView != null) {
            webView.removeJavascriptInterface("AndroidBridge");
            webView.destroy();
        }
        super.onDestroy();
    }
}
