// /your_custom_app/public/js/program_enrollment.js

frappe.ui.form.on('Program Enrollment', {

    onload: function(frm) {
        frm.set_query('academic_term', function() {
            return {
                'filters': {
                    'academic_year': frm.doc.academic_year
                }
            };
        });

        frm.set_query('academic_term', 'fees', function() {
            return {
                'filters': {
                    'academic_year': frm.doc.academic_year
                }
            };
        });

        frm.fields_dict['fees'].grid.get_field('fee_schedule').get_query = function(doc, cdt, cdn) {
            var d = locals[cdt][cdn];
            return {
                filters: { 'academic_term': d.academic_term }
            };
        };

        if (frm.doc.program) {
            frm.set_query('course', 'courses', function() {
                // Aquí cambiamos el método para que llame a tu versión personalizada de get_program_courses
                return {
                    query: 'integracion.integracion.program_override.get_program_courses',
                    filters: {
                        'program': frm.doc.program
                    }
                }
            });
        }

        frm.set_query('student', function() {
            // Sobrescribimos el método para obtener estudiantes
            return {
                query: 'integracion.integracion.program_override.get_students',
                filters: {
                }
            }
        });
    },

    program: function(frm) {
        frm.events.get_courses(frm);
        if (frm.doc.program) {
            frappe.call({
                method: 'education.education.api.get_fee_schedule',
                args: {
                    'program': frm.doc.program,
                    'student_category': frm.doc.student_category
                },
                callback: function(r) {
                    if (r.message) {
                        frm.set_value('fees', r.message);
                        frm.events.get_courses(frm);
                    }
                }
            });
        }
    },

    student_category: function() {
        frappe.ui.form.trigger('Program Enrollment', 'program');
    },

    get_courses: function(frm) {
        frm.program_courses = [];
        frm.set_value('courses', []);
        frappe.call({
            // Cambiamos para que use el método override de get_courses en el backend
            method: 'get_courses',
            doc: frm.doc,
            callback: function(r) {
                if (r.message) {
                    frm.program_courses = r.message;
                }
            }
        });
    }
});

frappe.ui.form.on('Program Enrollment Course', {
    courses_add: function(frm) {
        frm.fields_dict['courses'].grid.get_field('course').get_query = function(doc) {
            var course_list = [];
            if (!doc.__islocal) course_list.push(doc.name);
            $.each(doc.courses, function(_idx, val) {
                if (val.course) course_list.push(val.course);
            });
            return {
                filters: [
                    ['Course', 'name', 'not in', course_list],
                    ['Course', 'name', 'in', frm.program_courses.map((e) => e.course)]
                ]
            };
        };
    }
});
