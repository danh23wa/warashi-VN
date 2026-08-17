---
name: Bug report / 回報問題
about: Something in Warashi is broken / Warashi 有東西壞了
title: "[BUG] "
labels: bug
assignees: ''

---

<!--
This is the Warashi issue tracker. If your problem is with the upstream
Open-LLM-VTuber project rather than Warashi, please report it there instead.

這裡是 Warashi 的問題追蹤區。如果問題出在上游的 Open-LLM-VTuber 而不是
Warashi，請到那邊回報。
-->

### Checklist / 檢查項

- [ ] I removed API keys and other sensitive values from anything I pasted below.
      我已從下方貼上的內容移除 API key 等敏感資訊。
- [ ] I am on the latest Warashi release.
      我用的是最新版 Warashi。
- [ ] I searched existing issues in **this** repo.
      我搜尋過**這個** repo 的既有 issue。

---

### Environment / 環境

- **OS and version** / 作業系統與版本:
  <!-- e.g. macOS 15.2 Apple Silicon, or Windows 11 23H2 -->
- **Warashi version** / Warashi 版本:
  <!-- shown in the app, or the release tag you downloaded -->
- **How you installed** / 安裝方式:
  - [ ] Release zip / 發布包
  - [ ] From source / 原始碼
- **Where the LLM runs** / 大腦跑在哪:
  <!-- e.g. local Ollama qwen2.5:3b / an API / another machine on the LAN -->

If the problem involves **voice or audio**, please also fill in:
如果問題跟**語音或聲音**有關，請補上：

- `asr_model` in your `conf.yaml`:
- `tts_model` in your `conf.yaml`:

---

### What happened / 發生了什麼

<!--
What did you do, what did you expect, what happened instead?
你做了什麼、預期看到什麼、實際發生什麼？
-->

### How to reproduce / 如何重現

1.
2.
3.

---

### Backend log / 後端日誌

<!--
This is the single most useful thing you can attach. Most reports cannot be
acted on without it. Remember to strip API keys.

這是最有用的東西。沒有它多數問題無法處理。記得先把 API key 拿掉。
-->

```
paste log here / 日誌貼這裡
```

### Screenshots or frontend console / 截圖或前端主控台

<!-- Frontend console: press F12. Optional but helpful for UI problems. -->
<!-- 前端主控台：按 F12。UI 問題附上會很有幫助。 -->
