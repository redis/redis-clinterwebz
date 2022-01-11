.PHONY: run up svc

run:
	python3 app.py

up: dependencies
up:
	docker build -f docker/flask/Dockerfile -t interwebz/flask:latest .
	docker build -f docker/redis/Dockerfile -t interwebz/redis:unstable .
	# cat kube/deployment.yaml | sed "s/__VERSION__/$(version)/g" | kubectl apply -f -

svc: dependencies
svc:
	cat kube/deployment.yaml | sed "s/__VERSION__/$(version)/g" | kubectl apply -f -

dependencies:
	kubectl apply -f kube/config-map.yaml
	kubectl apply -f kube/service.yaml
	kubectl apply -f kube/ingress.yaml

clean:
	kubectl delete configmap/flask-nginx configmap/flask service/flask ingress.networking.k8s.io/flask deployment.apps/flask
	docker images | grep localhost | awk '{print $$3}' | uniq | xargs docker rmi -f