function addButtonWhenNavbarIsReady() {
    let navbar = document.querySelector('.navbar .container .navbar-collapse');

    if (navbar) {
        // Agregar CSS directamente desde JavaScript
        const style = document.createElement('style');
        style.innerHTML = `
            .custom-btn {
                background-color: #0080FF;
                color: white;
                font-size: 12px; /* Ajusta el tamaño de la fuente para hacerlo más pequeño */
                padding: 5px 10px; /* Ajusta el relleno para que el botón sea más compacto */
                border-radius: 4px; /* Bordes ligeramente redondeados */
                border: none; /* Elimina el borde predeterminado */
                cursor: pointer; /* Cambia el cursor a una mano al pasar sobre el botón */
                margin-right: 10px; /* Espacio a la derecha para separar del campo de búsqueda */
            }
            .custom-btn:hover {
                background-color: darkblue; /* Cambia el color al pasar el cursor por encima */
            }
        `;
        document.head.appendChild(style);

        // Verificar si el usuario tiene el rol "Asistencia"
        if (frappe.user.has_role("Asistencia")) {
            // Crear el botón
            let button = document.createElement('button');
            button.className = 'custom-btn'; // Aplicamos la clase personalizada

            button.textContent = 'Registro de Asistencia';
            button.onclick = function() {
                window.location.href = '/registro-asistencia';
            };

            // Insertar el botón justo antes del campo de búsqueda
            let searchBar = navbar.querySelector('.search-bar');
            if (searchBar) {
                searchBar.parentNode.insertBefore(button, searchBar);
            } else {
                setTimeout(addButtonWhenNavbarIsReady, 500); // Reintenta en 500ms
            }
        }
    } else {
        setTimeout(addButtonWhenNavbarIsReady, 500); // Reintenta en 500ms
    }
}

document.addEventListener("DOMContentLoaded", addButtonWhenNavbarIsReady);
