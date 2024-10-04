frappe.pages['user-profile'].on_page_load = function(wrapper) {
    // Llama al bundle original de la página
    frappe.require("user_profile_controller.bundle.js", () => {
        let user_profile = new frappe.ui.UserProfile(wrapper);
        user_profile.show();

        // Esperar a que la barra de herramientas esté disponible
        function addCustomButton() {
            let navbar = document.querySelector('.page-head .page-actions');
            
            if (navbar) {
                // Agregar estilos CSS dinámicamente desde JavaScript
                const style = document.createElement('style');
                style.innerHTML = `
                    .custom-orange-btn {
                        background-color: #ff7f0e;
                        color: white;
                        font-size: 12px;
                        padding: 5px 10px;
                        border-radius: 4px;
                        border: none;
                        cursor: pointer;
                        margin-left: 10px;
                    }
                    .custom-orange-btn:hover {
                        background-color: #e67300;
                    }
                `;
                document.head.appendChild(style); // Añadir los estilos al documento

                // Crear el botón personalizado en HTML y añadirle los estilos
                let customButton = document.createElement('button');
                customButton.className = 'custom-orange-btn';
                customButton.textContent = 'Registro de Asistencia';
                
                // Añadir funcionalidad de redirección
                customButton.onclick = function() {
                    window.location.href = '/registro-asistencia';  // Redirige a la página de asistencia
                };

                // Añadir el botón al contenedor de acciones en la barra
                navbar.appendChild(customButton);
            } else {
                // Si no se encuentra la barra, intentar de nuevo después de un corto retraso
                setTimeout(addCustomButton, 500); 
            }
        }

        // Sobrescribir la función `setup_user_search` para ocultar el botón después de ser creado
        frappe.ui.UserProfile.prototype.setup_user_search = function() {
            this.$user_search_button = this.page.set_secondary_action(
                __("Change User"),
                () => this.show_user_search_dialog(),
                { icon: "change", size: "sm" }
            );
            
            // Ocultar el botón de "Cambiar usuario" después de crearlo
            if (this.$user_search_button) {
                this.$user_search_button.hide(); // Ocultar usando el método de jQuery
            }
        };

        // Llamar a la función que agrega el botón personalizado
        addCustomButton();
    });
};
