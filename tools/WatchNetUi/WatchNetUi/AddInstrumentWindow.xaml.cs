using System.Globalization;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Controls.Primitives;
using System.Windows.Input;
using System.Windows.Media;

namespace WatchNetUi;

public partial class AddInstrumentWindow : Window
{
    public string SecCode { get; private set; } = "";
    public string ClassCode { get; private set; } = "TQBR";

    private static readonly CultureInfo Ru = CultureInfo.GetCultureInfo("ru-RU");

    private QuikSecDump.Snapshot _dump = QuikSecDump.Load();
    private bool _syncingChips;
    private string _classMode = "TQBR"; // TQBR | SPBFUT | CRYPTO | OTHER

    public AddInstrumentWindow()
    {
        InitializeComponent();
        ApplyDumpToUi();
        _syncingChips = true;
        ChipTqbr.IsChecked = true;
        _syncingChips = false;
        RefreshList();
        TxtSearch.Focus();
    }

    private void ApplyDumpToUi()
    {
        TxtDumpStatus.Text = _dump.Status;
        TxtDumpStatus.Foreground = _dump.Rows.Count > 0
            ? new SolidColorBrush(Color.FromRgb(0x7C, 0xC9, 0x8B))
            : new SolidColorBrush(Color.FromRgb(0xE0, 0xA3, 0x5A));

        var known = new HashSet<string>(StringComparer.OrdinalIgnoreCase) { "TQBR", "SPBFUT" };
        var others = _dump.Rows
            .Select(r => r.ClassCode)
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .Where(c => !known.Contains(c))
            .OrderBy(c => c, StringComparer.OrdinalIgnoreCase)
            .ToList();

        CmbOtherClass.Items.Clear();
        if (others.Count > 0)
        {
            CmbOtherClass.Visibility = Visibility.Visible;
            foreach (var c in others)
                CmbOtherClass.Items.Add(c);
            if (CmbOtherClass.SelectedIndex < 0)
                CmbOtherClass.SelectedIndex = 0;
        }
        else
        {
            CmbOtherClass.Visibility = Visibility.Collapsed;
        }
    }

    private void ClassChip_Checked(object sender, RoutedEventArgs e)
    {
        if (_syncingChips || sender is not ToggleButton chip) return;
        _syncingChips = true;
        ChipTqbr.IsChecked = ReferenceEquals(chip, ChipTqbr);
        ChipSpbfut.IsChecked = ReferenceEquals(chip, ChipSpbfut);
        ChipCrypto.IsChecked = ReferenceEquals(chip, ChipCrypto);
        _syncingChips = false;

        if (ChipCrypto.IsChecked == true) _classMode = "CRYPTO";
        else if (ChipSpbfut.IsChecked == true) _classMode = "SPBFUT";
        else if (ChipTqbr.IsChecked == true) _classMode = "TQBR";
        RefreshList();
    }

    private void ClassChip_Unchecked(object sender, RoutedEventArgs e)
    {
        if (_syncingChips) return;
        if (ChipTqbr.IsChecked != true && ChipSpbfut.IsChecked != true && ChipCrypto.IsChecked != true)
        {
            _syncingChips = true;
            ((ToggleButton)sender).IsChecked = true;
            _syncingChips = false;
        }
    }

    private void CmbOtherClass_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (!IsLoaded || CmbOtherClass.SelectedItem == null) return;
        _syncingChips = true;
        ChipTqbr.IsChecked = false;
        ChipSpbfut.IsChecked = false;
        ChipCrypto.IsChecked = false;
        _syncingChips = false;
        _classMode = "OTHER";
        RefreshList();
    }

    private void TxtSearch_TextChanged(object sender, TextChangedEventArgs e) => RefreshList();

    private void RefreshList()
    {
        string? cls = _classMode switch
        {
            "TQBR" => "TQBR",
            "SPBFUT" => "SPBFUT",
            "CRYPTO" => null,
            "OTHER" => CmbOtherClass.SelectedItem?.ToString(),
            _ => "TQBR",
        };
        var cryptoOnly = _classMode == "CRYPTO";
        if (cryptoOnly) cls = null;

        var rows = QuikSecDump.Filter(_dump.Rows, cls, TxtSearch.Text, cryptoOnly);
        var items = rows.Select(r => new SecRowVm(r)).ToList();
        var prev = GridSec.SelectedItem as SecRowVm;
        GridSec.ItemsSource = items;
        TxtCount.Text = items.Count == 0 ? "пусто" : $"{items.Count}";

        if (prev != null)
        {
            var again = items.FirstOrDefault(i =>
                i.Sec.Equals(prev.Sec, StringComparison.OrdinalIgnoreCase)
                && i.ClassCode.Equals(prev.ClassCode, StringComparison.OrdinalIgnoreCase));
            if (again != null) GridSec.SelectedItem = again;
        }
        if (GridSec.SelectedItem == null && items.Count > 0)
            GridSec.SelectedIndex = 0;
    }

    private void BtnReloadDump_Click(object sender, RoutedEventArgs e)
    {
        _dump = QuikSecDump.Load();
        ApplyDumpToUi();
        RefreshList();
    }

    private void GridSec_MouseDoubleClick(object sender, MouseButtonEventArgs e)
    {
        if (GridSec.SelectedItem != null)
            BtnOk_Click(sender, e);
    }

    private void GridSec_PreviewKeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key == Key.Enter && GridSec.SelectedItem != null)
        {
            BtnOk_Click(sender, e);
            e.Handled = true;
        }
    }

    private void BtnOk_Click(object sender, RoutedEventArgs e)
    {
        string sec;
        string cls;
        if (GridSec.SelectedItem is SecRowVm choice)
        {
            sec = choice.Row.Sec;
            cls = choice.Row.ClassCode;
        }
        else
        {
            sec = (TxtSearch.Text ?? "").Trim();
            var dash = sec.IndexOf(" — ", StringComparison.Ordinal);
            if (dash > 0) sec = sec[..dash].Trim();
            cls = _classMode switch
            {
                "SPBFUT" => "SPBFUT",
                "CRYPTO" => "SPBFUT",
                "OTHER" => CmbOtherClass.SelectedItem?.ToString() ?? "TQBR",
                _ => "TQBR",
            };
        }

        if (string.IsNullOrWhiteSpace(sec))
        {
            MessageBox.Show(this, "Выберите инструмент или введите sec_code в поиске", "Добавить",
                MessageBoxButton.OK, MessageBoxImage.Warning);
            return;
        }

        if (GridSec.SelectedItem == null && !string.IsNullOrWhiteSpace(TxtSearch.Text))
            sec = TxtSearch.Text.Trim();

        SecCode = sec;
        ClassCode = cls.Trim().ToUpperInvariant();
        DialogResult = true;
    }

    private void BtnCancel_Click(object sender, RoutedEventArgs e) => DialogResult = false;

    private sealed class SecRowVm(QuikSecDump.Row row)
    {
        public QuikSecDump.Row Row { get; } = row;
        public string Sec => Row.Sec;
        public string ClassCode => Row.ClassCode;
        public string Name =>
            string.IsNullOrWhiteSpace(Row.Name) ? Row.ShortName : Row.Name;

        public double? Last => Row.Last;
        public double? PriceStep => Row.PriceStep;
        public double? ValToday => Row.ValToday;
        public double? VolToday => Row.VolToday;

        public string LastText => FmtNum(Row.Last);
        public string PriceStepText => FmtNum(Row.PriceStep);
        public string ValTodayText => FmtMoney(Row.ValToday);
        public string VolTodayText => FmtNum(Row.VolToday, decimals: 0);

        public DateTime? ExpirySort =>
            Row.MatDate == null
                ? null
                : Row.MatDate.Value.Date + (Row.MatTime ?? TimeSpan.Zero);

        public string ExpiryText
        {
            get
            {
                if (Row.MatDate == null) return "";
                var d = Row.MatDate.Value.ToString("dd.MM.yyyy", Ru);
                if (Row.MatTime == null) return d;
                return d + " " + Row.MatTime.Value.ToString(@"hh\:mm");
            }
        }

        private static string FmtNum(double? v, int? decimals = null)
        {
            if (v == null) return "";
            if (decimals != null)
                return v.Value.ToString("N" + decimals, Ru);
            var abs = Math.Abs(v.Value);
            if (abs >= 1000) return v.Value.ToString("N2", Ru);
            if (abs >= 1) return v.Value.ToString("N4", Ru).TrimEnd('0').TrimEnd(',', '.');
            return v.Value.ToString("0.######", Ru);
        }

        private static string FmtMoney(double? v)
        {
            if (v == null) return "";
            var x = v.Value;
            if (Math.Abs(x) >= 1_000_000_000)
                return (x / 1_000_000_000).ToString("0.##", Ru) + " млрд";
            if (Math.Abs(x) >= 1_000_000)
                return (x / 1_000_000).ToString("0.##", Ru) + " млн";
            if (Math.Abs(x) >= 1_000)
                return (x / 1_000).ToString("0.#", Ru) + " тыс";
            return x.ToString("N0", Ru);
        }
    }
}
