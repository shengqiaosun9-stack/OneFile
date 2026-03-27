# Streamlit UI/UX Before/After（2026-03-28）

## 参考 Before 截图
- Landing（登录页）: `/Users/joesun/Documents/Screenshot 2026-03-28 at 1.17.27 AM.png`
- List / Card: `/Users/joesun/Documents/Screenshot 2026-03-28 at 1.07.14 AM.png`
- Create Modal: `/Users/joesun/Documents/Screenshot 2026-03-28 at 1.07.51 AM.png`
- Detail: `/Users/joesun/Documents/Screenshot 2026-03-28 at 1.07.35 AM.png`
- Share/List context: `/Users/joesun/Documents/Screenshot 2026-03-28 at 1.07.22 AM.png`

## Landing（登录）
1. 从单列弱层级表单改为左右双区：左侧价值叙事，右侧登录卡，首屏可读性明显提升。
2. 登录区加入实时邮箱校验与字段级提示，非法输入不再沉默失败。
3. 仅保留一个主 CTA（进入项目空间），并强化隐私与可信微文案，提升转化确定性。

## List（项目列表）
1. 卡片视觉统一到低色彩体系，减少多色状态干扰，阶段差异改用明度/边框/字重表达。
2. 卡片动作层级固定：主 CTA 统一为“查看完整档案”，其余动作收敛为次级。
3. 卡片信息保留“状态/活跃/下一步”核心结构，降低无关视觉噪音。

## Detail（项目详情）
1. 增加首屏 Focus Panel，明确三要素：Current Stage / Current Status / Next Action。
2. 首屏主动作规则固定（Owner=编辑项目，访客=创建我的项目档案），避免操作竞争。
3. 详情与列表/分享统一同一 token 体系，减少跨页风格跳变。

## Share（分享页）
1. 主 CTA 规则通过统一映射函数收敛（Owner/访客分支一致可控）。
2. 视觉风格对齐站内低色彩体系，减少外链页与站内页断层感。
3. 保持 share -> cta -> create/update 的归因链路不变，仅增强触达清晰度。

## Create / Update Modal（创建与更新弹窗）
1. 提交前先给输入引导（caption），减少初始错误提示造成的心理负担。
2. 主 CTA 在可提交条件满足前禁用，避免点击后才报错。
3. 创建与更新两类弹窗的主次动作节奏统一，反馈模型一致（submitting/error/success）。

## 验证说明
- 自动化测试：`backend/tests` 全量通过（36 passed）。
- 本地 smoke：`python3 -m streamlit run app.py --server.port 8502` 启动成功并返回 200。
- 说明：当前会话内置 Playwright 无法直连本机 `localhost`，因此 after 图建议在你本机页面直接核对（代码已完成并可运行）。
