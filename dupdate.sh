#!/bin/bash

# This automatically changes the directory to wherever this script is located
cd "$(dirname "$0")" || exit 1

declare -a active_containers
declare -a active_images

function validateContainers(){
	# Uses Docker's native -q flag to grab ONLY the container IDs
	readarray -t active_containers < <(docker ps -aq)
	[[ ${#active_containers[@]} -eq 0 ]] && { echo "No hay contenedores"; return 1 ; }
	return 0
}

function validateImages(){
	# Uses Docker's native -q flag to grab ONLY the image IDs
	readarray -t active_images < <(docker images -q)
	[[ ${#active_images[@]} -eq 0 ]] && { echo "No hay imagenes"; return 1 ; }
	return 0
}

function remove_containers(){
	# We can pass the array directly to docker rm instead of looping
	if ! docker rm -f "${active_containers[@]}"; then
		echo "Failed to remove containers"
		return 1
	fi
	echo "Containers removed successfully"
	unset active_containers
	return 0
}

function remove_images(){
	# We can pass the array directly to docker rmi instead of looping
	if ! docker rmi -f "${active_images[@]}"; then
		echo "Failed to remove images"
		return 1
	fi
	echo "Images removed successfully"
	unset active_images
	return 0
}

function composer(){
	if ! docker compose up -d --build; then 
		echo "No se pudo ejecutar el compose"
		return 1
	fi
	echo "Docker corriendo"
	return 0
}

if validateContainers; then
	remove_containers
fi

if validateImages; then
	remove_images
fi

composer
