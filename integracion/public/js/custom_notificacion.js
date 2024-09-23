$(document).ready(function() {
    //console.log('Escuchando evento show_notification...');
    frappe.realtime.on('show_notification', function(data) {
        //console.log('Evento show_notification recibido:', data);

        if (data.message && data.link) {
            let alert_html = `
                <div>
                    Se te ha asignado un nuevo documento: ${data.message}.
                    <a href="${data.link}" id="alert-link" target="_blank" style="color: blue; text-decoration: underline;">Ir al Documento</a>
                </div>
            `;

            // Mostrar la alerta con un temporizador de 1000 segundos
            let alert = frappe.show_alert({
                message: alert_html,
                indicator: 'blue'
            }, 10000);  // Temporizador de 10000 segundos (1000 * 1000 ms = 1,000,000 ms)

            // Cerrar la alerta si el usuario hace clic en el enlace
            $('#alert-link').on('click', function() {
                alert.hide();  // Cierra la alerta cuando el usuario hace clic en el enlace
            });
        } else {
            console.log('Datos de evento no recibidos correctamente.');
        }
    });
});
