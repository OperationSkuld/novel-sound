# iOS TrollStore 自签 IPA 构建

`ios-trollstore.yml` 在 GitHub Actions 的 macOS runner 上把 `pubspec.yaml` 当前版本（如 `v1.0.207`）的源码编译为 iOS 真机包，
并用 `ldid` 伪签名成 TrollStore 可安装的 IPA。整个过程不需要 Apple 开发者账号、描述文件或
私钥，也没有 7 天签名有效期。

## 为什么是这种签名

TrollStore 利用 CoreTrust 校验漏洞安装应用，支持 iOS 14.0–16.6.1、16.7 RC 和 17.0
（iPhone 14 / iOS 16.1 在范围内）。伪签名方式由 TrollStore 官方文档给出：

```
ldid -S<entitlements.plist> <binary>
```

安装时 TrollStore 会用假根证书重签并保留 entitlements。因此这里对 App 包内所有 Mach-O
（主程序、动态库、framework）逐个执行 `ldid -Sios/entitlements/trollstore.plist`，
entitlements 故意留空：不需要额外私有权限，避免误用 iOS 15+ 上被封禁的三项权限。

这不是 App Store / TestFlight 签名，也**不能**用普通侧载工具或信任证书的方式安装；
必须通过 TrollStore 打开 IPA。

## 构建链

| 步骤 | 内容 |
| --- | --- |
| Runner | `macos-15`，显式选择 Xcode 26.2（iOS SDK 26） |
| Flutter | 3.50.0，`flutter pub get --enforce-lockfile` |
| Rust | 1.99.1，`aarch64-apple-ios`，`scripts/build_rust_ios.sh` 产出静态库 |
| Pods | CocoaPods，禁用 Swift Package Manager |
| 编译 | `flutter build ios --release --no-codesign` |
| 签名打包 | `scripts/sign_ios_trollstore.sh`：ldid 伪签名 → zip → SHA-256 |
| 交付 | Actions Artifact + 仓库 Release |

Rust 核心必须以 `staticlib` 链接进主可执行文件，不能用 dlsym 加载bundle内的动态库；
相关原因和构建设置见 `IOS.md`。

## 在本地复现

需要 macOS + Xcode 26.2 + Flutter 3.50.0 + Rust 1.99.1 + `brew install ldid cocoapods`：

```bash
flutter config --no-enable-swift-package-manager
flutter pub get --enforce-lockfile
bash scripts/build_rust_ios.sh
(cd ios && pod install)
flutter build ios --release --no-codesign --no-pub
bash scripts/sign_ios_trollstore.sh build/ios/iphoneos/Runner.app dist/fqapp-ios-trollstore.ipa
```

## 安装与验证边界

1. 下载 IPA 到 iPhone，用 TrollStore 打开安装。不要在普通侧载工具里重签。
2. 图标缓存重载后若应用无法启动，在 TrollStore 设置里安装 Persistence Helper。
3. 卸载需进入 TrollStore 的应用列表左滑删除，桌面长按卸载不可用。
4. CI 只证明编译、签名、包结构和 SHA-256 通过；搜索、书架、阅读、播放、登录、后台音频、
   文件分享等仍需在真机上验证。
