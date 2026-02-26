# ApplicationSets

- **applications** ([appset-applications.yaml](appset-applications.yaml)): App generic (definitions trong [argocd/apps/definitions/](../apps/definitions/)) × config theo env (list dev, prod trong AppSet). Matrix sinh meo-station-backend-dev/prod, meo-station-database-dev/prod. Không liệt kê từng file backend/database per env.
- **infrastructure-apps** ([appset-infrastructure.yaml](appset-infrastructure.yaml)): Ingress-nginx trên mỗi cluster.
