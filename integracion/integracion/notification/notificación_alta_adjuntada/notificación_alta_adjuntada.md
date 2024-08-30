<h3>Archivo de Alta Adjuntado</h3>

<p>El archivo de alta ha sido adjuntado en la hoja de contratación <a href="{{ frappe.utils.get_url_to_form(doc.doctype, doc.name) }}">{{ doc.name }}</a>. Por favor, revisa los detalles a continuación:</p>

<h4>Detalles</h4>

<ul>
<li><strong>Nombre del Candidato/Empleado:</strong> {{ doc.applicant_name }}</li>
<li><strong>Email del Candidato/Empleado:</strong> {{ doc.email }}</li>
<li><strong>URL del Archivo de Alta:</strong> <a href="{{ doc.custom_alta }}">Archivo</a></li>
</ul>

<p>{% if comments %}</p>

<p><strong>Último comentario:</strong> "{{ comments[-1].comment }}" por {{ comments[-1].by }}</p>

<p>{% endif %}</p>
