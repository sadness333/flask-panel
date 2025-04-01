function calculateAge(birthYear) {
    try {
        const parts = birthYear.split('.');
        if (parts.length !== 3) {
            return "Некорректный формат";
        }

        const day = parseInt(parts[0]);
        const month = parseInt(parts[1]);
        const year = parseInt(parts[2]);

        const today = new Date();
        const birthDate = new Date(year, month - 1, day);

        let years = today.getFullYear() - birthDate.getFullYear();
        let months = today.getMonth() - birthDate.getMonth();
        let days = today.getDate() - birthDate.getDate();

        if (days < 0) {
            months--;
            // Получаем количество дней в предыдущем месяце
            const lastMonth = new Date(today.getFullYear(), today.getMonth() - 1, 1);
            const daysInLastMonth = new Date(today.getFullYear(), today.getMonth(), 0).getDate();
            days += daysInLastMonth;
        }

        if (months < 0) {
            years--;
            months += 12;
        }

        return formatAge(years, months);
    } catch (error) {
        return "Ошибка в дате";
    }
}

function formatAge(years, months) {
    function formatYears(years) {
        if (years === 0) {
            return "";
        }
        if (years % 10 === 1 && years % 100 !== 11) {
            return `${years} год`;
        }
        if ([2, 3, 4].includes(years % 10) && (years % 100 < 10 || years % 100 >= 20)) {
            return `${years} года`;
        }
        return `${years} лет`;
    }

    function formatMonths(months) {
        if (months === 0) {
            return "";
        }
        if (months % 10 === 1 && months % 100 !== 11) {
            return `${months} месяц`;
        }
        if ([2, 3, 4].includes(months % 10) && (months % 100 < 10 || months % 100 >= 20)) {
            return `${months} месяца`;
        }
        return `${months} месяцев`;
    }

    const parts = [formatYears(years), formatMonths(months)];
    return parts.filter(Boolean).join(" ");
}