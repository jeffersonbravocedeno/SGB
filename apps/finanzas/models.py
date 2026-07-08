from django.db import models


class Prestamo(models.Model):
    idprestamo = models.IntegerField(primary_key=True)
    idsocio = models.ForeignKey('socios.Socio', models.DO_NOTHING, db_column='idsocio')
    montoprestamosolicitado = models.DecimalField(max_digits=12, decimal_places=2)
    tasainteres = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    montototalpagar = models.DecimalField(max_digits=12, decimal_places=2)
    saldopendiente = models.DecimalField(max_digits=12, decimal_places=2)
    numerocuotas = models.IntegerField(blank=True, null=True)
    fechasolicitud = models.DateField()
    fechavencimiento = models.DateField()
    estadoprestamo = models.CharField(max_length=20)

    def __str__(self):
        return f'Prestamo {self.idprestamo}'

    class Meta:
        managed = False
        db_table = 'prestamo'
        verbose_name = 'Prestamo'
        verbose_name_plural = 'Prestamos'


class PrestamoGarante(models.Model):
    ESTADO_ACTIVO = 'Activo'
    ESTADO_INACTIVO = 'Inactivo'
    ESTADO_CHOICES = (
        (ESTADO_ACTIVO, 'Activo'),
        (ESTADO_INACTIVO, 'Inactivo'),
    )

    idprestamogarante = models.IntegerField(primary_key=True)
    idprestamo = models.ForeignKey('finanzas.Prestamo', models.DO_NOTHING, db_column='idprestamo')
    idgarante = models.ForeignKey('socios.Socio', models.DO_NOTHING, db_column='idgarante')
    capacidadcalculada = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    fecharegistro = models.DateTimeField()
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default=ESTADO_ACTIVO)

    def __str__(self):
        return f'Garante {self.idgarante_id} para prestamo {self.idprestamo_id}'

    class Meta:
        managed = False
        db_table = 'prestamo_garante'
        verbose_name = 'Garante de prestamo'
        verbose_name_plural = 'Garantes de prestamos'


class Pago(models.Model):
    idpago = models.IntegerField(primary_key=True)
    idprestamo = models.ForeignKey('finanzas.Prestamo', models.DO_NOTHING, db_column='idprestamo')
    idmetodopago = models.ForeignKey('configuracion.Metodopago', models.DO_NOTHING, db_column='idmetodopago')
    montopagado = models.DecimalField(max_digits=10, decimal_places=2)
    numeroreferencia = models.CharField(unique=True, max_length=50, blank=True, null=True)
    fechapago = models.DateTimeField()
    fechaconfirmacionadmin = models.DateTimeField(blank=True, null=True)
    comprobantepago = models.CharField(max_length=255, blank=True, null=True)
    estadopago = models.CharField(max_length=20, blank=True, null=True)

    def __str__(self):
        return self.numeroreferencia or f'Pago {self.idpago}'

    class Meta:
        managed = False
        db_table = 'pago'
        verbose_name = 'Pago'
        verbose_name_plural = 'Pagos'


class Ahorro(models.Model):
    idahorro = models.IntegerField(primary_key=True)
    idsocio = models.ForeignKey('socios.Socio', models.DO_NOTHING, db_column='idsocio')
    idbingo = models.ForeignKey('bingos.Bingo', models.DO_NOTHING, db_column='idbingo')
    tipoahorro = models.CharField(max_length=50)
    montoahorro = models.DecimalField(max_digits=10, decimal_places=2)
    fechaahorro = models.DateTimeField()
    comentarioahorro = models.CharField(max_length=100, blank=True, null=True)
    estado = models.CharField(max_length=25)

    def __str__(self):
        return f'Ahorro {self.idahorro} - {self.tipoahorro}'

    class Meta:
        managed = False
        db_table = 'ahorro'
        verbose_name = 'Ahorro'
        verbose_name_plural = 'Ahorros'


class Aportesemanal(models.Model):
    idaporte = models.IntegerField(primary_key=True)
    idsocio = models.ForeignKey('socios.Socio', models.DO_NOTHING, db_column='idsocio')
    idregalo = models.ForeignKey('configuracion.Regalo', models.DO_NOTHING, db_column='idregalo')
    idpartida = models.ForeignKey('bingos.Partidabingo', models.DO_NOTHING, db_column='idpartida', blank=True, null=True)
    numerosemana = models.IntegerField(blank=True, null=True)
    fechaplanificadada = models.DateTimeField()
    fechaentregareal = models.DateTimeField(blank=True, null=True)
    metodoingreso = models.CharField(max_length=50)
    referenciaingreso = models.CharField(max_length=100, blank=True, null=True)
    estadoaporte = models.CharField(max_length=20, blank=True, null=True)

    def __str__(self):
        semana = self.numerosemana if self.numerosemana is not None else self.idaporte
        return f'Aporte semana {semana}'

    class Meta:
        managed = False
        db_table = 'aportesemanal'
        verbose_name = 'Aporte semanal'
        verbose_name_plural = 'Aportes semanales'
