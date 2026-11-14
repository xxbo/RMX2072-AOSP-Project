"""Require same-boot primary PON and PS_HOLD evidence before cold-start testing."""
import re
from uuid import UUID


def check_power_ready(text, boot):
    UUID(boot)
    if set(re.findall(r'^M1POWER boot=(.*)$',text,re.M))!={boot}:
        raise ValueError('Power snapshot is absent or belongs to another boot')
    required=[
        'DEVICE=0-00 DRIVER=/sys/bus/spmi/drivers/pmic-spmi',
        'PLATFORM=c264000.restart DRIVER=/sys/bus/platform/drivers/msm-restart',
    ]
    if any(line not in text.splitlines() for line in required):
        raise ValueError('Primary PMIC, PON or PS_HOLD driver is not bound')
    primary='c440000.qcom,spmi:qcom,pm8150@0:'
    canonical=[
        'PLATFORM='+primary+'pon@800 DRIVER=/sys/bus/platform/drivers/qcom-pon',
        'PLATFORM='+primary+'pon@800:pwrkey DRIVER=/sys/bus/platform/drivers/pm8941-pwrkey',
    ]
    legacy='PLATFORM='+primary+'qcom,power-on@800 DRIVER=/sys/bus/platform/drivers/pm8941-pwrkey'
    if all(line in text.splitlines() for line in canonical) and legacy not in text.splitlines():
        binding='upstream-pon-parent-pwrkey-child'
        revision=re.findall(re.escape(primary+'pon@800:pwrkey: ')+r'PON revision=(\d+) subtype=4; upstream binding',text)
    elif legacy in text.splitlines() and not any(line in text.splitlines() for line in canonical):
        binding='legacy-m1-alias'
        revision=re.findall(r'RMX2072 primary PON revision=(\d+) subtype=4; preserving pull/debounce',text)
    else:
        raise ValueError('Primary PON binding is absent or ambiguous')
    if len(revision)!=1:
        raise ValueError('No verified GEN2_PRIMARY PON read in this boot')
    result=dict(boot_id=boot,primary_spmi_sid=0,pon_revision=int(revision[0]),
                pon_subtype=4,pon_driver='pm8941-pwrkey',poweroff_driver='msm-restart')
    if binding=='upstream-pon-parent-pwrkey-child':result['binding']=binding
    return result
