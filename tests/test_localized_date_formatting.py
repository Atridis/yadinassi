"""Explicit Russian local policy and official examples, not synthetic native goldens."""
from decimal import Decimal, localcontext
import unittest
from unittest.mock import patch

from yadinassi import Interpreter, BSLError
from yadinassi.dates import BSLDate, date, UnsupportedDateRange
from yadinassi.date_formatting import date_tokens
from yadinassi.formatting import format_value
from yadinassi.values import NULL, to_string


class LocalizedDateFormattingTests(unittest.TestCase):
    def setUp(self):
        self.value = date('20020820153309')

    def test_official_russian_mask_example(self):
        self.assertEqual(format_value(self.value, 'ДФ="дд ММММ гггг \'г.\' ЧЧ:мм:сс"'),
                         '20 августа 2002 г. 15:33:09')
        self.assertEqual(format_value(self.value, 'ДФ="дд/ММ-гггг"'), '20/08-2002')

    def test_official_local_date_examples(self):
        for style, expected in (('ДД', '20 августа 2002 г.'), ('Д', '20.08.2002'), ('В', '15:33:09')):
            with self.subTest(style=style):
                self.assertEqual(format_value(self.value, 'ДЛФ='+style), expected)
        self.assertEqual(format_value(date('20051120140323'), 'ДЛФ=ДДВ'),
                         '20 ноября 2005 г. 14:03:23')

    def test_all_local_style_aliases(self):
        for english, russian, expected in (
            ('D', 'Д', '20.08.2002'), ('DD', 'ДД', '20 августа 2002 г.'),
            ('T', 'В', '15:33:09'), ('DT', 'ДВ', '20.08.2002 15:33:09'),
            ('DDT', 'ДДВ', '20 августа 2002 г. 15:33:09')):
            for name in ('DLF','ДЛФ','dlf','длф'):
                for style in (english,russian):
                    with self.subTest(name=name,style=style):
                        self.assertEqual(format_value(self.value,name+'='+style), expected)

    def test_russian_numeric_tokens_are_exact_case_sensitive_aliases(self):
        for russian, english in (('д','d'),('дд','dd'),('М','M'),('ММ','MM'),
            ('г','y'),('гг','yy'),('гггг','yyyy'),('к','q'),('ч','H'),('чч','HH'),
            ('Ч','H'),('ЧЧ','HH'),('м','m'),('мм','mm'),('с','s'),('сс','ss')):
            with self.subTest(token=russian):
                self.assertEqual(format_value(self.value,'ДФ='+russian),format_value(self.value,'DF='+english))
        self.assertEqual(format_value(self.value,"DF='М:м M:m'"),'8:33 8:33')

    def test_year_without_century_and_quarter(self):
        for year, expected in ((1,'1 01 0001'),(99,'99 99 0099'),(100,'0 00 0100'),
                               (2000,'0 00 2000'),(2001,'1 01 2001'),(9999,'99 99 9999')):
            with self.subTest(year=year):
                self.assertEqual(format_value(date(f'{year:04}0102'),"DF='y yy yyyy'"),expected)
        for month in range(1,13):
            self.assertEqual(format_value(date(f'2026{month:02}01'),'ДФ=к'),str((month-1)//3+1))

    def test_all_months_nominal_and_day_genitive(self):
        names=('Январь','Февраль','Март','Апрель','Май','Июнь','Июль','Август','Сентябрь','Октябрь','Ноябрь','Декабрь')
        genitive=('января','февраля','марта','апреля','мая','июня','июля','августа','сентября','октября','ноября','декабря')
        for month,(name,part) in enumerate(zip(names,genitive),1):
            value=date(f'2026{month:02}02')
            with self.subTest(month=month):
                self.assertEqual(format_value(value,'DF=MMMM'),name)
                self.assertEqual(format_value(value,"DF='d MMMM'"),'2 '+part)
                self.assertEqual(format_value(value,"ДФ='ММММ дд'"),part+' 02')

    def test_literal_day_letters_do_not_select_genitive(self):
        self.assertEqual(format_value(self.value,'DF="\'d\' MMMM"'),'d Август')
        self.assertEqual(format_value(self.value,'DF="\'дд\' ММММ"'),'дд Август')

    def test_quoted_literals_and_bare_multiword_fallback_preserved(self):
        self.assertEqual(format_value(self.value,'DF="yyyy \'Q\'q"'),'2002 Q3')
        self.assertEqual(format_value(self.value,'DF="yyyy\'\'MM"'),'200208')
        self.assertEqual(format_value(self.value,'DF="yyyy\';\'ММ"'),'2002;08')
        self.assertEqual(format_value(self.value,'DF=d MMMM yyyy'),to_string(self.value))

    def test_explicit_russian_locale_is_host_independent(self):
        with patch('locale.setlocale',side_effect=AssertionError('host locale forbidden')):
            self.assertEqual(format_value(self.value,'L=ru;DLF=DD'),'20 августа 2002 г.')
        for locale in ('en','ru_RU','RU','ru-RU',''):
            with self.subTest(locale=locale),self.assertRaises(ValueError):
                format_value(self.value,'L='+locale+';DLF=D')

    def test_empty_date_precedence_and_first_second(self):
        self.assertEqual(format_value(BSLDate(0),'DLF=DDT'),'')
        self.assertEqual(format_value(BSLDate(0),"DE='empty';DLF=DDT"),'empty')
        self.assertEqual(format_value(BSLDate(0),"DE='';DLF=DDT"),'1 января 0001 г. 00:00:00')
        self.assertEqual(format_value(BSLDate(10000),"DE='empty';DLF=T"),'00:00:01')
        self.assertEqual(format_value(date('99991231235959'),'DLF=DDT'),'31 декабря 9999 г. 23:59:59')

    def test_fractional_ticks_preserve_existing_whole_second_policy(self):
        a=self.value
        self.assertEqual(format_value(BSLDate(a.ticks+9999),'DLF=DDT'),format_value(a,'DLF=DDT'))
        with self.assertRaises(UnsupportedDateRange):format_value(BSLDate(0,boundary=True),'DLF=D')

    def test_existing_date_alias_selection_remains_unchanged(self):
        self.assertEqual(format_value(self.value,'DF=yyyy;ДФ=к'),'3')
        self.assertEqual(format_value(self.value,'DF=к;DF=yyyy'),'3')
        self.assertEqual(format_value(BSLDate(0),"DE='a';ДП='b';DLF=D"),'b')

    def test_equivalent_local_styles_can_repeat_but_conflicts_fail_closed(self):
        self.assertEqual(format_value(self.value,'DLF=D;ДЛФ=Д'),'20.08.2002')
        for spec in ('DLF=D;DLF=T','DLF=D;ДЛФ=В','DF=yyyy;DLF=D','DLF=D;ДФ=yyyy'):
            with self.subTest(spec=spec),self.assertRaises(ValueError):format_value(self.value,spec)

    def test_invalid_local_order_and_noncanonical_forms_fail_closed(self):
        for style in ('TD','TDD','ВД','ВДД','DDD','DTT','d','dd','dt','DD T','D/T',''):
            with self.subTest(style=style),self.assertRaises(ValueError):format_value(self.value,'DLF='+style)

    def test_invalid_or_not_yet_calibrated_tokens_fail_closed(self):
        for token in ('yyy','yyyа','qq','кк','ггг','DD','YYYY','MMMMM','МММММ','h','hh','tt','вв','ddd','dddd','MMM'):
            with self.subTest(token=token),self.assertRaises(ValueError):format_value(self.value,'DF='+token)
        with self.assertRaises(ValueError):format_value(self.value,'DF="yyyy \'broken"')

    def test_expansion_and_input_limits_are_utf16_bounded(self):
        for spec in ("DF='"+'MMMM/'*800+"'",'DE='+'😀'*2049,'DLF='+'D'*4096):
            with self.subTest(length=len(spec)),self.assertRaises(ValueError):format_value(self.value,spec)
        self.assertEqual(format_value(self.value,'DF="\''+'😀'*2042+'\'"'),'😀'*2042)

    def test_non_date_values_keep_family_specific_presentation(self):
        for value in ('text',True,False,Decimal('1.25'),NULL,None):
            with self.subTest(kind=type(value).__name__):
                self.assertEqual(format_value(value,'DLF=D'),format_value(value,''))
        self.assertEqual(format_value(True,"DLF=DD;BT='yes'"),'yes')

    def test_decimal_context_is_neither_used_nor_modified(self):
        with localcontext() as context:
            context.prec=1
            for flag in context.traps:context.traps[flag]=True
            context.clear_flags();before=dict(context.flags)
            self.assertEqual(format_value(self.value,'DLF=DD'),'20 августа 2002 г.')
            self.assertEqual(dict(context.flags),before)

    def test_bsl_aliases_eval_and_catchable_errors(self):
        vm=Interpreter()
        try:
            vm.execute('D=Date(2002,8,20,15,33,9); A=Формат(D,"ДЛФ=ДД"); '
                       'B=Eval("Format(D, ""DLF=DD"")");')
            self.assertEqual(vm.variables['a'],'20 августа 2002 г.')
            self.assertEqual(vm.variables['a'],vm.variables['b'])
            with self.assertRaises(BSLError):vm.execute('Format(D,"DLF=TD");')
        finally:vm.close()

    def test_token_scanner_rejects_host_values_without_hooks(self):
        class Hostile(str):
            def __len__(self):raise AssertionError('host length')
        with self.assertRaises(TypeError):date_tokens(Hostile('d'))


if __name__=='__main__':unittest.main()
