.PHONY: help push-kaggle pull-kaggle-status train dev

help:
	@echo "Ringside Analytics — common tasks"
	@echo ""
	@echo "  make push-kaggle        Push ml/notebooks/ringside_ml.ipynb to Kaggle"
	@echo "  make pull-kaggle-status Show latest Kaggle kernel run status"
	@echo "  make train              Retrain ML models (ml/train.py)"
	@echo "  make dev                Start docker-compose dev stack"

push-kaggle:
	@test -f ~/.kaggle/kaggle.json || { echo "Missing ~/.kaggle/kaggle.json"; exit 1; }
	cd ml/notebooks && kaggle kernels push -p .

pull-kaggle-status:
	kaggle kernels status theodorerubin/ringside-analytics-ml

train:
	cd ml && python train.py

dev:
	docker compose up -d
