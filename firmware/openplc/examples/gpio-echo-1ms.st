(* Same as gpio-echo.st with a 1 ms task interval: used for the input-to-output latency
   measurements in docs/10-latency.md (variant "OpenPLC, 1 ms cycle"). *)
PROGRAM main
  VAR
    q0 AT %QX0.0 : BOOL;
    q1 AT %QX0.1 : BOOL;
    i0 AT %IX0.0 : BOOL;
    cmd AT %QX1.0 : BOOL;
    ain0 AT %IW0 : UINT;
    ain0_copy AT %QW0 : UINT;
  END_VAR
  VAR
    blink : TON;
    blink_off : TON;
  END_VAR

  q0 := cmd OR i0;
  ain0_copy := ain0;

  blink(IN := NOT blink_off.Q, PT := T#500ms);
  blink_off(IN := blink.Q, PT := T#500ms);
  q1 := blink.Q;
END_PROGRAM

CONFIGURATION Config0
  RESOURCE Res0 ON PLC
    TASK task0(INTERVAL := T#1ms, PRIORITY := 0);
    PROGRAM instance0 WITH task0 : main;
  END_RESOURCE
END_CONFIGURATION
