#!/bin/bash

declare -a active_containers
declare -a active_images
function validateContainers(){
	readarray -t active_containers < <(docker ps -a | awk 'NR > 1 { print $1 }')
	[[ ${#active_containers[@]} -eq 0 ]] && { echo "No hay contenedores"; return 1 ; }
#	echo ${active_containers}
	return 0
}

function validateImages(){
	readarray -t active_images < <(docker images | awk 'NR > 1 { print $2 }')
	[[ ${#active_images[@]} -eq 0 ]] && { echo "No hay imagenes"; return 1 ; }
#	echo ${active_images}
#	echo ${active_images}
	return 0
}

function remove_containers(){
for container in ${active_containers[@]};do
	if ! docker rm -f "$container";then
		echo "Failed to remove container $container"
		return 1
	fi
done
echo "Containers removed succeslfully"
unset active_containers
return 0
}

function remove_images(){
for image in ${active_images[@]};do
	if ! docker rmi -f "$image";then
		echo "Failed to remove image $image"
		return 1
	fi
done
echo "Images removed successfully"
unset active_images
return 0
}

function composer(){
	if ! docker compose up -d --build;then 
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
