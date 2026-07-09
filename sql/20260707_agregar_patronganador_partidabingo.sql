BEGIN;

ALTER TABLE partidabingo
ADD COLUMN patronganador VARCHAR(20) NOT NULL DEFAULT 'carton_lleno';

ALTER TABLE partidabingo
ADD CONSTRAINT chk_partidabingo_patronganador
CHECK (
    patronganador IN (
        'carton_lleno',
        'linea_horizontal',
        'linea_vertical',
        'diagonal',
        'cuatro_esquinas',
        'cruz',
        'x'
    )
);

COMMIT;
