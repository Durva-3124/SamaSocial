import {
  splitTypographyProps,
  usePageTypography,
  type PageTypographyProps,
} from "./landing-pages/pageTypography";
import { LandingPageFrame, type LandingPageProps } from "./landing-pages/LandingPageFrame";
import { KAGE_TYPOGRAPHY } from "./landing-pages/pageRecipes";

export function KageLandingPage(props: LandingPageProps & PageTypographyProps) {
  const [type, frame] = splitTypographyProps(props);
  const customization = usePageTypography(KAGE_TYPOGRAPHY, type);
  return <LandingPageFrame {...frame} customization={customization} title="Samasocial — Learn with clarity" sourceUrl="/landing-pages/kage.html" />;
}