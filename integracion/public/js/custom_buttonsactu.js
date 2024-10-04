function addButtonWhenNavbarIsReady() {
    let navbar = document.querySelector('.navbar .container .navbar-collapse');

    if (navbar) {
        // Agregar CSS directamente desde JavaScript
        const style = document.createElement('style');
        style.innerHTML = `
            .custom-btn {
                background-color: #0080FF;
                color: white;
                font-size: 12px;
                padding: 5px 10px;
                border-radius: 4px;
                border: none;
                cursor: pointer;
                margin-right: 10px;
            }
            .custom-btn:hover {
                background-color: darkblue;
            }
            .custom-btn i {
                margin-right: 5px; /* Espacio entre el ícono y el texto */
            }
        `;
        document.head.appendChild(style);

        // Verificar si el usuario tiene el rol "Asistencia"
        if (frappe.user.has_role("Asistencia")) {
            // Crear el botón
            let button = document.createElement('button');
            button.className = 'custom-btn'; // Aplicamos la clase personalizada

            // Crear el ícono que será usado en vista móvil
            const icon = document.createElement('i');
            icon.className = 'fa-regular fa-user';

            // Añadir el texto "Mi Perfil" inicialmente
            button.textContent = 'Mi Perfil';

            button.onclick = function() {
                window.location.href = '/app/user-profile';
            };

            // Insertar el botón justo antes del campo de búsqueda
            let searchBar = navbar.querySelector('.search-bar');
            if (searchBar) {
                searchBar.parentNode.insertBefore(button, searchBar);
            } else {
                setTimeout(addButtonWhenNavbarIsReady, 500); // Reintenta en 500ms
            }

            // Función para cambiar a ícono en vista móvil
            function updateButtonForMobile() {
                if (window.innerWidth <= 768) { // Si la pantalla es igual o menor que 768px (tamaño móvil)
                    if (!button.querySelector('i')) { // Añadir el ícono si no está ya presente
                        button.innerHTML = ''; // Limpia el texto
                        button.appendChild(icon); // Añadir el ícono
                    }
                } else {
                    if (button.querySelector('i')) { // Volver a texto si estamos en vista de escritorio
                        button.innerHTML = 'Mi Perfil';
                    }
                }
            }

            // Ejecutar al cargar
            updateButtonForMobile();

            // Ejecutar cada vez que cambie el tamaño de la ventana
            window.addEventListener('resize', updateButtonForMobile);
        }
    } else {
        setTimeout(addButtonWhenNavbarIsReady, 500); // Reintenta en 500ms
    }
}

document.addEventListener("DOMContentLoaded", addButtonWhenNavbarIsReady);
