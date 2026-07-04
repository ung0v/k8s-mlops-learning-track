.PHONY: help
help:
	@echo "Stage targets:"
	@echo "  make 00-bootstrap      # verify cluster + install ingress-nginx"
	@echo "  make 01-fundamentals   # apply pods/deploy/svc"
	@echo "  make 04-jobs           # run training Job + CronJob"
	@echo "  make 05-serving        # deploy FastAPI serving + Ingress + HPA"
	@echo "  make 09-mlflow          # install MLflow server"
	@echo "  make 15-up             # capstone: bring up the full stack"

.PHONY: 00-bootstrap
00-bootstrap:
	@echo "Checking cloud-provider-kind is running..."
	@pgrep -f cloud-provider-kind >/dev/null || echo "WARNING: cloud-provider-kind not running. Start it in a separate terminal: sudo \$$(go env GOPATH)/bin/cloud-provider-kind --enable-default-ingress=true"
	@kubectl get nodes
	@echo "Cluster ready. See 00-bootstrap/README.md for the full setup including native ingress."

.PHONY: 01-fundamentals
01-fundamentals:
	kubectl apply -f 01-k8s-fundamentals/manifests/

.PHONY: 04-jobs
04-jobs:
	kubectl apply -f 04-batch-ml-jobs/manifests/

.PHONY: 05-serving
05-serving:
	kubectl apply -f 05-serving-single-model/manifests/

.PHONY: 09-mlflow
09-mlflow:
	kubectl apply -f 09-mlflow-tracking/manifests/

.PHONY: 15-up
15-up:
	@echo "Capstone not implemented yet — see 15-capstone/README.md"