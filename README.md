# ens3 软件源

这个仓库同时承载 ens3 的 GitHub Pages 和正式 rootless 软件源。客户端添加源时使用 Pages 的公开 URL，并从 `repo/` 下载索引和 `.deb`。

正式源的约束：

- 仅接收 `iphoneos-arm64` 的标准 rootless `.deb`。
- 每个包 ID 仅保留最高的稳定三段式版本；历史包在对应 Tweak 的 GitHub Release。
- `Packages` 和 `Release` 由 `scripts/rebuild-repo.py` 从实际 `.deb` 生成，禁止手工维护校验字段。
- 当前不签名；哈希只保证文件完整性，不代表发布者身份认证。

当 Tweak 的稳定 tag workflow 用 `PUBLISH_REPO_TOKEN` 推送新的 `.deb` 时，`.github/workflows/update-repo.yml` 会校验所有包、清理同包旧版本、重建元数据、部署 Pages，并从公网复核 `Release`、`Packages` 和每个 `.deb` 的大小及 SHA256。

详细开发与发布规则见 [`jailbreak-development`](https://github.com/ens3de/jailbreak-development) 中的 `PROJECT-STANDARDS.md`。
