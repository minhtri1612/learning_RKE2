# Application layer: generic app + config theo env

- **App generic:** `definitions/*.yaml` — mỗi file mô tả một app (name, path, namespace, syncWave). Thêm app = thêm file trong definitions.
- **Config dựa trên môi trường:** `config/*.yaml` — mỗi file = một env (dev.yaml, prod.yaml): env, project, clusterName, valueFileSuffix, targetRevision. Thêm env = thêm file trong config (vd. config/staging.yaml).
- **Matrix:** ApplicationSet đọc config/* × definitions/* → sinh Application cho từng cặp (env × app).
