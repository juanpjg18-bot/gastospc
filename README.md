# Mis Gastos

Registro personal de gastos mensuales y cuentas fijas, con recordatorio automático
el día 1 de cada mes de cuánto dinero se necesita para pagar las cuentas.

## Uso

```bash
python3 app.py
```

Abrí http://127.0.0.1:5000 en el navegador.

- **Resumen**: total necesario para pagar las cuentas fijas del mes, total gastado
  y desglose por categoría.
- **Gastos**: cargá gastos puntuales (fecha, categoría, monto, descripción).
- **Cuentas fijas**: cargá tus cuentas recurrentes (alquiler, servicios, etc.) con
  monto y día de vencimiento. Se pueden activar/desactivar sin borrarlas.

Cada cambio se guarda en `data/cuentas.json` y `data/gastos.json`, y se sincroniza
automáticamente a GitHub (`git add` + `commit` + `push` en segundo plano) para que
el recordatorio automático del día 1 de cada mes pueda leer los datos actualizados.

## Recordatorio automático

Una rutina programada en la nube (Claude Code) revisa `data/cuentas.json` el día 1
de cada mes y envía una notificación con el total a pagar.
