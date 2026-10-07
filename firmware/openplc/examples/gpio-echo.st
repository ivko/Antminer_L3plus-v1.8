(* OpenPLC test program for the Antminer I/O module (antminer hardware layer).
   Modbus map used by the OpenPLC runtime:
     %QX0.0..%QX99.7 -> coils 0..799      (%QX0.n = GPIO line "Qn" via the hardware layer)
     %IX0.0..%IX99.7 -> discrete inputs  (%IX0.n = GPIO line "In")
     %IW0..          -> input registers  (%IW0..7 = ADC channels AIN0..7, 12 bit)
   Coil 8 (%QX1.0) is a "software command" written from the Modbus master; Q0 follows it
   or the physical input I0. Q1 blinks at 1 Hz so the board shows the program is running.
   ADC channel 0 is copied to holding register 0 (%QW0) so a master can read it as 4x0001. *)
PROGRAM main
  VAR
    q0 AT %QX0.0 : BOOL;
    q1 AT %QX0.1 : BOOL;
    i0 AT %IX0.0 : BOOL;
    cmd AT %QX1.0 : BOOL;
    ain0 AT %IW0 : UINT;
    ain0_copy AT %QW0 : UINT;
  END_VAR
  (* matiec: a VAR block holds either located (AT) variables or plain ones, never both *)
  VAR
    blink : TON;
    blink_off : TON;
  END_VAR

  q0 := cmd OR i0;
  ain0_copy := ain0;

  (* 500 ms on / 500 ms off *)
  blink(IN := NOT blink_off.Q, PT := T#500ms);
  blink_off(IN := blink.Q, PT := T#500ms);
  q1 := blink.Q;
END_PROGRAM

CONFIGURATION Config0
  RESOURCE Res0 ON PLC
    TASK task0(INTERVAL := T#50ms, PRIORITY := 0);
    PROGRAM instance0 WITH task0 : main;
  END_RESOURCE
END_CONFIGURATION
