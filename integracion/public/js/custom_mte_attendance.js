// Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt

frappe.query_reports["Monthly Attendance Sheet"] = {
    filters: [
        {
            fieldname: "month",
            label: __("Mes"),
            fieldtype: "Select",
            reqd: 1,
            options: [
                { value: 1, label: __("Ene") },
                { value: 2, label: __("Feb") },
                { value: 3, label: __("Mar") },
                { value: 4, label: __("Abr") },
                { value: 5, label: __("May") },
                { value: 6, label: __("Jun") },
                { value: 7, label: __("Jul") },
                { value: 8, label: __("Ago") },
                { value: 9, label: __("Sep") },
                { value: 10, label: __("Oct") },
                { value: 11, label: __("Nov") },
                { value: 12, label: __("Dic") },
            ],
            default: frappe.datetime.str_to_obj(frappe.datetime.get_today()).getMonth() + 1,
        },
        {
            fieldname: "year",
            label: __("Año"),
            fieldtype: "Select",
            reqd: 1,
        },
        {
            fieldname: "employee",
            label: __("Empleado"),
            fieldtype: "Link",
            options: "Employee",
            get_query: () => {
                var company = frappe.query_report.get_filter_value("company");
                return {
                    filters: {
                        company: company,
                    },
                };
            },
        },
        {
            fieldname: "company",
            label: __("Empresa"),
            fieldtype: "Link",
            options: "Company",
            default: frappe.defaults.get_user_default("Company"),
            reqd: 1,
        },
        {
            fieldname: "group_by",
            label: __("Agrupar por"),
            fieldtype: "Select",
            options: ["", "Sucursal", "Grado", "Departamento", "Designación"],
        },
        {
            fieldname: "summarized_view",
            label: __("Vista resumida"),
            fieldtype: "Check",
            default: 0,
        },
    ],
    onload: function () {
        return frappe.call({
            method: "hrms.hr.report.monthly_attendance_sheet.monthly_attendance_sheet.get_attendance_years",
            callback: function (r) {
                var year_filter = frappe.query_report.get_filter("year");
                year_filter.df.options = r.message;
                year_filter.df.default = r.message.split("\n")[0];
                year_filter.refresh();
                year_filter.set_input(year_filter.df.default);
            },
        });
    },
    formatter: function (value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);
        const summarized_view = frappe.query_report.get_filter_value("summarized_view");
        const group_by = frappe.query_report.get_filter_value("group_by");

        // Traducción de los estados de asistencia
        const status_translation = {
            "P": "Presente",
            "A": "Ausente",
            "HD": "Medio Día",
            "WFH": "Teletrabajo",
            "L": "Permiso",
            "H": "Festivo",
            "WO": "Descanso Semanal"
        };

        // Traducción de días de la semana
        const days_translation = {
            "Mon": "Lun",
            "Tue": "Mar",
            "Wed": "Mié",
            "Thu": "Jue",
            "Fri": "Vie",
            "Sat": "Sáb",
            "Sun": "Dom"
        };

        // Traducir los días de la semana en la columna si es necesario
        if (Object.keys(days_translation).includes(value)) {
            value = days_translation[value];
        }

        // Traducir los estados de asistencia
        if (Object.keys(status_translation).includes(value)) {
            value = status_translation[value];
        }

        if (group_by && column.colIndex === 1) {
            value = "<strong>" + value + "</strong>";
        }

        if (!summarized_view) {
            if ((group_by && column.colIndex > 3) || (!group_by && column.colIndex > 2)) {
                if (value == "Presente" || value == "Teletrabajo")
                    value = "<span style='color:green'>" + value + "</span>";
                else if (value == "Ausente")
                    value = "<span style='color:red'>" + value + "</span>";
                else if (value == "Medio Día")
                    value = "<span style='color:orange'>" + value + "</span>";
                else if (value == "Permiso")
                    value = "<span style='color:#318AD8'>" + value + "</span>";
            }
        }

        return value;
    },
};
