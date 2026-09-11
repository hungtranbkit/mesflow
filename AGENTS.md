# mesflow

Read and obey the workspace rules first:

`../AGENTS.md`

Project directory:
`mesflow/`

Do not modify sibling projects unless the task explicitly requires a cross-project change.

## Kỹ năng cấp dự án

`skills/` chứa quy trình mà agent phải theo, không phải tài liệu tham khảo.

- **`skills/visual-ui-audit/SKILL.md`** — bắt buộc khi thay đổi chạm
  CSS/layout/DOM của `app/mesflow/web/`, kể cả khi test hiện có đã xanh.
  Quy trình QA cho thay đổi UI:
  `functional -> DOM/style contract -> responsive screenshot audit -> visual review -> merge`
